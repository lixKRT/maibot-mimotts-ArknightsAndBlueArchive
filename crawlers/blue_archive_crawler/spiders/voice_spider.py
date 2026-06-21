"""蔚蓝档案语音爬虫。

从 Gamekee Wiki API 获取学生语音数据，提取各语言的音频 URL，并生成台词台本。
"""

import asyncio
import json
import logging
from pathlib import Path
from dataclasses import dataclass

import aiohttp

from crawlers.blue_archive_crawler.items import CrawlResult, VoiceItem
from crawlers.blue_archive_crawler.pipelines import VoicePipeline
from crawlers.blue_archive_crawler.settings import CrawlerSettings

logger = logging.getLogger("blue_archive_crawler.voice_spider")


@dataclass
class VoiceScript:
    """语音台词数据。"""
    filename: str = ""      # 文件名（英文）
    title_cn: str = ""      # 原中文名
    text_cn: str = ""       # 中文台词
    text_jp: str = ""       # 日语台词
    text_kr: str = ""       # 韩语台词

# 语言列索引映射（0-based）
LANGUAGE_COLUMNS = {
    "jp": 4,
    "cn": 6,
    "kr": 7,
}

# 语言中文名到英文代码映射（用于解析用户输入）
LANGUAGE_NAME_MAP = {
    "日语": "jp",
    "中文": "cn",
    "韩语": "kr",
}

# 分类中文到英文映射
CATEGORY_MAP = {
    "通常": "usual",
    "大厅及咖啡馆": "cafe",
    "好感度": "bond",
    "战斗": "battle",
    "成长": "growth",
    "事件": "event",
    "活动": "activity",
}

# API 模板
CONTENT_API = "https://api-cdn.gamekee.com/wiki2.0/pro/829/content/{student_id}.json"


class VoiceSpider:
    """语音爬虫。"""

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings

    async def crawl(
        self,
        student_name: str,
        student_id: str,
        languages: list[str] | None = None,
        output_dir: str | None = None,
    ) -> CrawlResult:
        """爬取指定学生的语音资源。"""
        if languages is None:
            languages = ["jp", "kr"]
        # 将中文语言名转换为英文代码
        languages = [LANGUAGE_NAME_MAP.get(lang, lang) for lang in languages]

        result = CrawlResult(student_name=student_name)
        out_dir = Path(output_dir or self.settings.output_dir)

        api_url = CONTENT_API.format(student_id=student_id)
        json_data = await self._fetch_api(api_url)
        if json_data is None:
            result.failed = 1
            result.errors.append(f"无法获取学生「{student_name}」(ID: {student_id}) 的 API 数据")
            return result

        items, scripts = self._parse_voice_items(json_data, student_name, languages, out_dir)
        if not items:
            result.errors.append(f"学生「{student_name}」未找到任何语音数据")
            return result

        # 生成台词台本
        if scripts:
            safe_name = self._sanitize_filename(student_name)
            script_path = out_dir / safe_name / "script.md"
            self._generate_script_md(scripts, student_name, script_path)

        pipeline = VoicePipeline(self.settings)
        await pipeline.process(items, result)

        return result

    def _generate_script_md(self, scripts: list[VoiceScript], student_name: str, save_path: Path) -> None:
        """生成台词台本 markdown 文件。"""
        save_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        lines.append(f"# {student_name} 语音台本\n")

        for script in scripts:
            lines.append(f"# {script.filename} - {script.title_cn}\n")
            if script.text_jp:
                lines.append(f"**日语**: {script.text_jp}\n")
            if script.text_cn:
                lines.append(f"**中文**: {script.text_cn}\n")
            lines.append("")

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info("已生成台词台本: %s", save_path)
        except OSError as exc:
            logger.error("台词台本写入失败: %s - %s", save_path, exc)

    async def _fetch_api(self, url: str) -> dict | None:
        """请求 API 并返回 JSON 数据。"""
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)
        headers = {
            "User-Agent": self.settings.user_agent,
            "Referer": "https://www.gamekee.com/",
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning("API 请求失败 [HTTP %d]: %s", response.status, url)
                        return None
                    return await response.json()
        except asyncio.TimeoutError:
            logger.warning("API 请求超时: %s", url)
            return None
        except aiohttp.ClientError as e:
            logger.warning("API 请求错误: %s -> %s", url, e)
            return None
        except Exception as e:
            logger.warning("API 请求异常: %s -> %s", url, e)
            return None

    def _parse_voice_items(
        self,
        json_data: dict,
        student_name: str,
        languages: list[str],
        out_dir: Path,
    ) -> tuple[list[VoiceItem], list[VoiceScript]]:
        """从 API JSON 中解析语音数据项和台词。

        Returns:
            (voice_items, scripts) 元组
        """
        items: list[VoiceItem] = []
        scripts: list[VoiceScript] = []

        content = json_data.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return items, scripts
        if not isinstance(content, dict):
            return items, scripts

        base_data = content.get("baseData", [])
        if not isinstance(base_data, list):
            return items, scripts

        in_voice_section = False
        current_category = ""
        voice_header_found = False
        category_counters: dict[str, int] = {}

        for row in base_data:
            if not isinstance(row, list):
                continue

            first_cell = self._get_cell_value(row, 0)
            if first_cell and ("配音" in first_cell or "语音" in first_cell):
                if not voice_header_found:
                    voice_header_found = True
                    in_voice_section = True
                    continue
                continue

            if not in_voice_section:
                continue

            if first_cell and ("语言" in first_cell or "大类" in first_cell):
                continue

            if not row or all(self._get_cell_value(row, i) is None for i in range(len(row))):
                continue

            category = self._get_cell_value(row, 0)
            if category:
                if any(kw in category for kw in ["立绘", "表情", "设定", "CG", "图片"]):
                    break
                current_category = category

            title = self._get_cell_value(row, 1) or ""
            if not title:
                continue

            # 收集台词文本（第2列是日语文本，第3列是中文翻译）
            text_jp = self._get_cell_value(row, 2) or ""
            text_cn = self._get_cell_value(row, 3) or ""

            # 生成文件名
            category_en = CATEGORY_MAP.get(current_category, "other")
            if category_en not in category_counters:
                category_counters[category_en] = 0
            category_counters[category_en] += 1
            seq_num = category_counters[category_en]
            filename = f"{category_en}-{seq_num}"

            # 添加台词到台本
            scripts.append(VoiceScript(
                filename=filename,
                title_cn=title,
                text_cn=text_cn,
                text_jp=text_jp,
            ))

            # 为每种语言生成下载项
            safe_name = self._sanitize_filename(student_name)
            for lang in languages:
                col_index = LANGUAGE_COLUMNS.get(lang)
                if col_index is None:
                    continue

                audio_url = self._get_cell_value(row, col_index)
                if not audio_url or not self._is_audio_url(audio_url):
                    continue

                if audio_url.startswith("//"):
                    audio_url = "https:" + audio_url

                save_path = out_dir / safe_name / "voice" / lang / f"{filename}.ogg"

                items.append(VoiceItem(
                    student_name=student_name,
                    language=lang,
                    category=current_category,
                    title=title,
                    audio_url=audio_url,
                    save_path=str(save_path),
                ))

        return items, scripts

    @staticmethod
    def _get_cell_value(row: list, index: int) -> str | None:
        """安全地获取表格单元格的文本值。"""
        if index >= len(row):
            return None
        cell = row[index]
        if isinstance(cell, dict):
            val = cell.get("value")
            if val is not None:
                return str(val).strip() or None
            return None
        if isinstance(cell, str):
            return cell.strip() or None
        return None

    @staticmethod
    def _is_audio_url(url: str) -> bool:
        """判断 URL 是否为音频链接。"""
        audio_extensions = (".ogg", ".mp3", ".wav", ".m4a", ".aac", ".flac")
        lower = url.lower()
        return any(ext in lower for ext in audio_extensions)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符。"""
        if not name:
            return ""
        illegal = r'<>:"/\|?*'
        for ch in illegal:
            name = name.replace(ch, "_")
        return name.strip().strip(".")
