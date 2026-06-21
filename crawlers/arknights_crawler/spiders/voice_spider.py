"""语音爬虫 -- 从 PRTS Wiki 获取干员语音数据并下载音频文件，并生成台词台本。"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import aiohttp
from selectolax.parser import HTMLParser

from crawlers.arknights_crawler.items import VoiceItem
from crawlers.arknights_crawler.pipelines import VoicePipeline
from crawlers.arknights_crawler.settings import CrawlerSettings

logger = logging.getLogger(__name__)


@dataclass
class VoiceScript:
    """语音台词数据。"""
    filename: str = ""      # 文件名
    title_cn: str = ""      # 中文标题
    text_cn: str = ""       # 中文台词
    text_jp: str = ""       # 日语台词

# 语言代码到中文名称的映射
LANGUAGE_MAP = {
    "cn": "中文",
    "jp": "日语",
    "kr": "韩语",
    "en": "英语",
}


class VoiceSpider:
    """语音爬虫类。"""

    def __init__(self, settings: CrawlerSettings) -> None:
        self._settings = settings
        self._pipeline = VoicePipeline(delay=settings.download_delay)
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._settings.request_timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": self._settings.user_agent},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch_page(self, url: str) -> Optional[str]:
        session = await self._ensure_session()
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning("页面请求失败 [%d]: %s", response.status, url)
                return None
        except aiohttp.ClientError as exc:
            logger.error("页面请求异常: %s - %s", url, exc)
            return None

    async def get_operator_id(self, operator_name: str) -> Optional[str]:
        url = self._settings.get_voice_page_url(operator_name)
        html = await self.fetch_page(url)
        if not html:
            return None

        parser = HTMLParser(html)
        root_node = parser.css_first("div#voice-data-root")
        if root_node is None:
            logger.warning("未找到 voice-data-root 元素: %s", operator_name)
            return None

        operator_id = root_node.attributes.get("data-voice-key", "")
        if not operator_id:
            logger.warning("voice-data-root 缺少 data-voice-key 属性: %s", operator_name)
            return None

        logger.info("获取到干员 ID: %s -> %s", operator_name, operator_id)
        return operator_id

    def parse_voice_items(
        self,
        html: str,
        operator_name: str,
        operator_id: str,
        languages: list[str],
        output_dir: str,
    ) -> tuple[list[VoiceItem], list[VoiceScript]]:
        parser = HTMLParser(html)
        items: list[VoiceItem] = []
        scripts: list[VoiceScript] = []

        voice_nodes = parser.css("div.voice-data-item")
        if not voice_nodes:
            logger.warning("未找到语音数据项: %s", operator_name)
            return items, scripts

        for node in voice_nodes:
            title = (node.attributes.get("data-title") or "").strip()
            filename = (node.attributes.get("data-voice-filename") or "").strip()
            index = (node.attributes.get("data-voice-index") or "").strip()
            cond = (node.attributes.get("data-cond") or "").strip()

            if not filename:
                continue

            number_match = re.search(r"(\d+)", filename)
            if not number_match:
                logger.debug("无法从文件名提取编号: %s", filename)
                continue
            number = number_match.group(1)

            # 提取台词文本
            text_cn = ""
            text_jp = ""
            detail_nodes = node.css("div.voice-item-detail")
            for detail in detail_nodes:
                kind = (detail.attributes.get("data-kind-name") or "").strip()
                text = detail.text(deep=True, strip=True)
                if kind == "中文":
                    text_cn = text
                elif kind == "日文":
                    text_jp = text

            # 生成文件名（去掉扩展名）
            script_filename = f"cn_{number}"

            scripts.append(VoiceScript(
                filename=script_filename,
                title_cn=title,
                text_cn=text_cn,
                text_jp=text_jp,
            ))

            for lang in languages:
                lang_code = lang.lower()
                url = self._settings.get_voice_url(lang_code, operator_id, number)
                save_path = str(
                    Path(output_dir)
                    / operator_name
                    / "voice"
                    / lang_code
                    / f"{lang_code}_{number}.wav"
                )

                items.append(
                    VoiceItem(
                        operator_name=operator_name,
                        operator_id=operator_id,
                        title=title,
                        filename=filename,
                        number=number,
                        index=index,
                        cond=cond,
                        language=lang_code,
                        url=url,
                        save_path=save_path,
                    )
                )

        logger.info("解析到 %d 条语音（%d 种语言）: %s", len(voice_nodes), len(languages), operator_name)
        return items, scripts

    def _generate_script_md(self, scripts: list[VoiceScript], operator_name: str, save_path: Path) -> None:
        """生成台词台本 markdown 文件。"""
        save_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        lines.append(f"# {operator_name} 语音台本\n")

        for script in scripts:
            lines.append(f"# {script.filename} - {script.title_cn}\n")
            if script.text_cn:
                lines.append(f"**中文**: {script.text_cn}\n")
            if script.text_jp:
                lines.append(f"**日语**: {script.text_jp}\n")
            lines.append("")

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info("已生成台词台本: %s", save_path)
        except OSError as exc:
            logger.error("台词台本写入失败: %s - %s", save_path, exc)

    async def run(
        self,
        operator_name: str,
        languages: Optional[list[str]] = None,
        output_dir: Optional[str] = None,
    ) -> dict:
        if languages is None:
            languages = ["cn", "jp"]
        if output_dir is None:
            output_dir = self._settings.output_dir

        result = {
            "success": False,
            "character": operator_name,
            "game": "arknights",
            "voice_count": 0,
            "save_path": "",
            "error": "",
        }

        try:
            operator_id = await self.get_operator_id(operator_name)
            if not operator_id:
                result["error"] = "search fail"
                return result

            url = self._settings.get_voice_page_url(operator_name)
            html = await self.fetch_page(url)
            if not html:
                result["error"] = "无法获取语音页面"
                return result

            voice_items, scripts = self.parse_voice_items(html, operator_name, operator_id, languages, output_dir)

            if not voice_items:
                result["error"] = "未解析到语音数据"
                return result

            # 生成台词台本
            if scripts:
                script_path = Path(output_dir) / operator_name / "script.md"
                self._generate_script_md(scripts, operator_name, script_path)

            session = await self._ensure_session()
            tasks = [self._pipeline.process(item, session, self._semaphore) for item in voice_items]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = 0
            errors = []
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    errors.append(f"下载异常 [{voice_items[i].title}]: {res}")
                elif res:
                    success_count += 1

            if success_count > 0:
                result["success"] = True
                result["voice_count"] = success_count
                result["save_path"] = f"{output_dir}/{operator_name}"
            else:
                result["error"] = "所有语音下载失败"

            if errors:
                result["error"] = "; ".join(errors[:3])

        except Exception as exc:
            logger.error("语音爬取任务异常: %s - %s", operator_name, exc)
            result["error"] = f"任务异常: {exc}"
        finally:
            await self.close()

        return result
