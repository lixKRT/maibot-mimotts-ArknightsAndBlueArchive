"""蔚蓝档案立绘爬虫。

从 Gamekee Wiki API 获取学生立绘、表情、设定集、本家画、官方介绍、官方衍生等图片资源。
"""

import asyncio
import json
import logging
from pathlib import Path

import aiohttp

from crawlers.blue_archive_crawler.items import CrawlResult, IllustrationItem
from crawlers.blue_archive_crawler.pipelines import IllustrationPipeline
from crawlers.blue_archive_crawler.settings import CrawlerSettings

logger = logging.getLogger("blue_archive_crawler.illustration_spider")

# API 模板
CONTENT_API = "https://api-cdn.gamekee.com/wiki2.0/pro/829/content/{student_id}.json"

# 需要遍历查找图片的分类关键词
SCAN_CATEGORIES = {"设定集", "本家画", "官方介绍", "官方衍生"}

# 分类中文到英文映射
CATEGORY_EN_MAP = {
    "设定集": "setting",
    "本家画": "original",
    "官方介绍": "introduction",
    "官方衍生": "derivative",
}


class IllustrationSpider:
    """立绘爬虫。"""

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings

    async def crawl(
        self,
        student_name: str,
        student_id: str,
        output_dir: str | None = None,
    ) -> CrawlResult:
        """爬取指定学生的立绘资源。"""
        result = CrawlResult(student_name=student_name)
        out_dir = Path(output_dir or self.settings.output_dir)

        api_url = CONTENT_API.format(student_id=student_id)
        json_data = await self._fetch_api(api_url)
        if json_data is None:
            result.failed = 1
            result.errors.append(f"无法获取学生「{student_name}」(ID: {student_id}) 的 API 数据")
            return result

        items = self._parse_illustration_items(json_data, student_name, out_dir)
        if not items:
            result.errors.append(f"学生「{student_name}」未找到任何立绘数据")
            return result

        pipeline = IllustrationPipeline(self.settings)
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

    def _parse_illustration_items(
        self,
        json_data: dict,
        student_name: str,
        out_dir: Path,
    ) -> list[IllustrationItem]:
        """从 API JSON 中解析立绘数据项。"""
        items: list[IllustrationItem] = []

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

        for row in base_data:
            if not isinstance(row, list) or not row:
                continue

            first_cell_value = self._get_cell_value(row, 0)
            if not first_cell_value:
                continue

            if first_cell_value.startswith("立绘"):
                items.extend(self._parse_illustration_row(row, student_name, out_dir))
                continue

            if first_cell_value == "角色表情":
                items.extend(self._parse_expression_row(row, student_name, out_dir))
                continue

            if first_cell_value in SCAN_CATEGORIES:
                items.extend(self._parse_scan_category_row(row, student_name, out_dir))
                continue

        return items

    def _parse_illustration_row(
        self,
        row: list,
        student_name: str,
        out_dir: Path,
    ) -> list[IllustrationItem]:
        """解析立继行数据。"""
        items: list[IllustrationItem] = []

        image_url = self._get_cell_value(row, 2)
        if not image_url or not self._is_image_url(image_url):
            return items

        image_url = self._clean_image_url(image_url)

        safe_name = self._sanitize_filename(student_name)
        seq_num = len(items) + 1
        save_path = out_dir / safe_name / "illustration" / "costume" / f"{seq_num}.png"

        items.append(IllustrationItem(
            student_name=student_name,
            category="costume",
            name=str(seq_num),
            image_url=image_url,
            save_path=str(save_path),
        ))

        return items

    def _parse_expression_row(
        self,
        row: list,
        student_name: str,
        out_dir: Path,
    ) -> list[IllustrationItem]:
        """解析表情行数据。"""
        items: list[IllustrationItem] = []

        image_urls = self._extract_all_image_urls(row, start_col=1)

        for idx, url in enumerate(image_urls):
            url = self._clean_image_url(url)

            safe_name = self._sanitize_filename(student_name)
            save_path = out_dir / safe_name / "illustration" / "expression" / f"{idx + 1}.png"

            items.append(IllustrationItem(
                student_name=student_name,
                category="expression",
                name=str(idx + 1),
                image_url=url,
                save_path=str(save_path),
            ))

        return items

    def _parse_scan_category_row(
        self,
        row: list,
        student_name: str,
        out_dir: Path,
    ) -> list[IllustrationItem]:
        """解析需要遍历查找图片的分类行数据。"""
        items: list[IllustrationItem] = []
        category = self._get_cell_value(row, 0) or "其他"

        category_en = CATEGORY_EN_MAP.get(category, "other")

        image_urls = self._extract_all_image_urls(row, start_col=1)

        for idx, url in enumerate(image_urls):
            url = self._clean_image_url(url)

            safe_name = self._sanitize_filename(student_name)
            save_path = out_dir / safe_name / "illustration" / category_en / f"{idx + 1}.png"

            items.append(IllustrationItem(
                student_name=student_name,
                category=category_en,
                name=str(idx + 1),
                image_url=url,
                save_path=str(save_path),
            ))

        return items

    @staticmethod
    def _extract_all_image_urls(row: list, start_col: int = 0) -> list[str]:
        """从行数据中提取所有图片 URL。"""
        urls: list[str] = []

        for i in range(start_col, len(row)):
            cell = row[i]
            if not isinstance(cell, dict):
                continue

            cell_type = str(cell.get("type", "")).lower()
            cell_value = cell.get("value")

            if cell_type in ("image", "imageset"):
                if isinstance(cell_value, list):
                    for item in cell_value:
                        if isinstance(item, str) and item.strip():
                            urls.append(item.strip())
                elif isinstance(cell_value, str) and cell_value.strip():
                    urls.append(cell_value.strip())

        return urls

    @staticmethod
    def _get_cell_value(row: list, index: int) -> str | None:
        """安全地获取表格单元格的文本值。"""
        if index >= len(row):
            return None
        cell = row[index]
        if isinstance(cell, dict):
            val = cell.get("value")
            if isinstance(val, str):
                return val.strip() or None
            if val is not None:
                return str(val).strip() or None
            return None
        if isinstance(cell, str):
            return cell.strip() or None
        return None

    @staticmethod
    def _clean_image_url(url: str) -> str:
        """清理图片 URL，去掉 ?x-image-process= 后缀。"""
        marker = "?x-image-process="
        idx = url.find(marker)
        if idx != -1:
            url = url[:idx]
        marker2 = "&x-image-process="
        idx2 = url.find(marker2)
        if idx2 != -1:
            url = url[:idx2]

        if url.startswith("//"):
            url = "https:" + url

        return url

    @staticmethod
    def _is_image_url(url: str) -> bool:
        """判断 URL 是否为图片链接。"""
        image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
        lower = url.lower()
        return any(ext in lower for ext in image_extensions) or "image" in lower

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符。"""
        if not name:
            return ""
        illegal = r'<>:"/\|?*'
        for ch in illegal:
            name = name.replace(ch, "_")
        return name.strip().strip(".")
