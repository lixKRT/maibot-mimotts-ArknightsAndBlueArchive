"""干员信息爬虫 -- 从 PRTS Wiki 获取干员档案和立绘数据。"""

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import aiohttp
from selectolax.parser import HTMLParser

from crawlers.arknights_crawler.items import IllustrationItem, OperatorInfoItem
from crawlers.arknights_crawler.pipelines import ImagePipeline, TextPipeline
from crawlers.arknights_crawler.settings import CrawlerSettings

logger = logging.getLogger(__name__)


class InfoSpider:
    """干员信息爬虫类。"""

    def __init__(self, settings: CrawlerSettings) -> None:
        self._settings = settings
        self._text_pipeline = TextPipeline()
        self._image_pipeline = ImagePipeline(delay=settings.download_delay)
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

    @staticmethod
    def compute_md5(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    @staticmethod
    def extract_field(text: str, field_name: str) -> str:
        patterns = [
            rf"【{re.escape(field_name)}】\s*(.*?)(?=【|$)",
            rf"{re.escape(field_name)}[：:]\s*(.*?)(?=\n|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()
        return ""

    def parse_operator_info(self, html: str, operator_name: str, output_dir: str) -> OperatorInfoItem:
        parser = HTMLParser(html)
        item = OperatorInfoItem(
            operator_name=operator_name,
            save_path=str(Path(output_dir) / operator_name / "profile.txt"),
        )

        body = parser.body
        if body is None:
            logger.warning("页面 body 为空: %s", operator_name)
            return item

        page_text = body.text(deep=True)

        # 提取基础档案
        item.code_name = self.extract_field(page_text, "代号")
        item.gender = self.extract_field(page_text, "性别")
        item.combat_experience = self.extract_field(page_text, "战斗经验")
        item.birth_place = self.extract_field(page_text, "出身地")
        item.birthday = self.extract_field(page_text, "生日")
        item.race = self.extract_field(page_text, "种族")
        item.height = self.extract_field(page_text, "身高")
        item.infection_status = self.extract_field(page_text, "矿石病感染情况")

        # 提取六维属性
        item.physical_strength = self.extract_field(page_text, "物理强度")
        item.battlefield_mobility = self.extract_field(page_text, "战场机动")
        item.physiological_tolerance = self.extract_field(page_text, "生理耐受")
        item.tactical_planning = self.extract_field(page_text, "战术规划")
        item.combat_technique = self.extract_field(page_text, "战斗技巧")
        item.originium_arts_adaptability = self.extract_field(page_text, "源石技艺适应性")

        # 提取医疗数据
        item.cell_originium_assimilation = self.extract_field(page_text, "体细胞与源石融合率")
        item.blood_originium_crystal_density = self.extract_field(page_text, "血液源石结晶密度")

        # 提取档案资料
        item.objective_resume = self.extract_field(page_text, "客观履历")
        item.clinical_analysis = self.extract_field(page_text, "临床诊断分析")
        item.profile_1 = self.extract_field(page_text, "档案资料一")
        item.profile_2 = self.extract_field(page_text, "档案资料二")
        item.profile_3 = self.extract_field(page_text, "档案资料三")
        item.profile_4 = self.extract_field(page_text, "档案资料四")

        logger.info("已解析干员档案: %s", operator_name)
        return item

    def parse_illustrations(self, html: str, operator_name: str, output_dir: str) -> list[IllustrationItem]:
        items: list[IllustrationItem] = []

        stage_en_map = {
            "_1": "elite-0",
            "_2": "elite-2",
        }
        for suffix, stage_en in stage_en_map.items():
            raw_filename = f"立绘_{operator_name}{suffix}.png"
            filename = raw_filename.replace(" ", "_")
            md5_hash = self.compute_md5(filename)
            url = self._settings.get_image_url(filename, md5_hash)
            save_path = str(Path(output_dir) / operator_name / "illustration" / f"{stage_en}.png")

            items.append(
                IllustrationItem(
                    operator_name=operator_name,
                    stage=stage_en,
                    filename=filename,
                    url=url,
                    save_path=save_path,
                )
            )

        parser = HTMLParser(html)
        skin_items = self._parse_skin_info(parser, operator_name, output_dir)
        items.extend(skin_items)

        logger.info("解析到 %d 张立绘: %s", len(items), operator_name)
        return items

    def _parse_skin_info(self, parser: HTMLParser, operator_name: str, output_dir: str) -> list[IllustrationItem]:
        items: list[IllustrationItem] = []

        scripts = parser.css("script")
        for script in scripts:
            script_text = script.text(deep=False) or ""
            if "charskin_params" not in script_text:
                continue

            match = re.search(
                r"charskin_params\s*=\s*(\[.*?\])\s*;",
                script_text,
                re.DOTALL,
            )
            if not match:
                continue

            json_str = match.group(1)
            json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

            try:
                skin_data = json.loads(json_str)
            except json.JSONDecodeError as exc:
                logger.warning("皮肤数据 JSON 解析失败: %s - %s", operator_name, exc)
                continue

            for i, skin in enumerate(skin_data, start=1):
                raw_filename = f"立绘_{operator_name}_skin{i}.png"
                filename = raw_filename.replace(" ", "_")
                md5_hash = self.compute_md5(filename)
                url = self._settings.get_image_url(filename, md5_hash)
                save_path = str(Path(output_dir) / operator_name / "illustration" / f"skin-{i}.png")

                items.append(
                    IllustrationItem(
                        operator_name=operator_name,
                        stage=f"skin-{i}",
                        filename=filename,
                        url=url,
                        save_path=save_path,
                    )
                )

            break

        return items

    async def run(
        self,
        operator_name: str,
        output_dir: Optional[str] = None,
    ) -> dict:
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
            url = self._settings.get_operator_url(operator_name)
            html = await self.fetch_page(url)
            if not html:
                result["error"] = "search fail"
                return result

            info_item = self.parse_operator_info(html, operator_name, output_dir)
            self._text_pipeline.process(info_item)

            illustration_items = self.parse_illustrations(html, operator_name, output_dir)

            if illustration_items:
                session = await self._ensure_session()
                tasks = [
                    self._image_pipeline.process(item, session, self._semaphore)
                    for item in illustration_items
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

            result["success"] = True
            result["save_path"] = f"{output_dir}/{operator_name}"

        except Exception as exc:
            logger.error("干员信息爬取任务异常: %s - %s", operator_name, exc)
            result["error"] = f"任务异常: {exc}"
        finally:
            await self.close()

        return result

    async def check_operator_exists(self, operator_name: str) -> bool:
        try:
            url = self._settings.get_operator_url(operator_name)
            session = await self._ensure_session()
            async with session.get(url, allow_redirects=False) as response:
                exists = response.status == 200
                logger.debug("干员页面检查: %s -> %d (%s)", operator_name, response.status, "存在" if exists else "不存在")
                return exists
        except aiohttp.ClientError as exc:
            logger.error("干员页面检查请求异常: %s - %s", operator_name, exc)
            return False
        finally:
            await self.close()
