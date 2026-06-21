"""蔚蓝档案语音爬虫。

从 Gamekee Wiki API 获取学生语音数据，提取各语言的音频 URL。
"""

import asyncio
import json
import logging
from pathlib import Path

import aiohttp

from crawlers.blue_archive_crawler.items import CrawlResult, VoiceItem
from crawlers.blue_archive_crawler.pipelines import VoicePipeline
from crawlers.blue_archive_crawler.settings import CrawlerSettings

logger = logging.getLogger("blue_archive_crawler.voice_spider")

# 语言列索引映射（0-based）
LANGUAGE_COLUMNS = {
    "日语": 4,
    "中文": 6,
    "韩语": 7,
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
            languages = ["日语", "韩语"]

        result = CrawlResult(student_name=student_name)
        out_dir = Path(output_dir or self.settings.output_dir)

        api_url = CONTENT_API.format(student_id=student_id)
        json_data = await self._fetch_api(api_url)
        if json_data is None:
            result.failed = 1
            result.errors.append(f"无法获取学生「{student_name}」(ID: {student_id}) 的 API 数据")
            return result

        items = self._parse_voice_items(json_data, student_name, languages, out_dir)
        if not items:
            result.errors.append(f"学生「{student_name}」未找到任何语音数据")
            return result

        pipeline = VoicePipeline(self.settings)
        await pipeline.process(items, result)

        return result

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
    ) -> list[VoiceItem]:
        """从 API JSON 中解析语音数据项。"""
        items: list[VoiceItem] = []

        content = json_data.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return items
        if not isinstance(content, dict):
            return items

        base_data = content.get("baseData", [])
        if not isinstance(base_data, list):
            return items

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

            for lang in languages:
                col_index = LANGUAGE_COLUMNS.get(lang)
                if col_index is None:
                    continue

                audio_url = self._get_cell_value(row, col_index)
                if not audio_url or not self._is_audio_url(audio_url):
                    continue

                if audio_url.startswith("//"):
                    audio_url = "https:" + audio_url

                category_en = CATEGORY_MAP.get(current_category, "other")

                if category_en not in category_counters:
                    category_counters[category_en] = 0
                category_counters[category_en] += 1
                seq_num = category_counters[category_en]

                safe_name = self._sanitize_filename(student_name)
                filename = f"{category_en}-{seq_num}.ogg"
                save_path = out_dir / safe_name / "voice" / lang / filename

                items.append(VoiceItem(
                    student_name=student_name,
                    language=lang,
                    category=current_category,
                    title=title,
                    audio_url=audio_url,
                    save_path=str(save_path),
                ))

        return items

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
