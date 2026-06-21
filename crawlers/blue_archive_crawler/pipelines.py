"""下载管道：负责将爬取到的数据项保存到本地磁盘。"""

import asyncio
import logging
from pathlib import Path

import aiohttp

from crawlers.blue_archive_crawler.items import CrawlResult, IllustrationItem, VoiceItem
from crawlers.blue_archive_crawler.settings import CrawlerSettings

logger = logging.getLogger("blue_archive_crawler.pipelines")


class BasePipeline:
    """下载管道基类。"""

    def __init__(self, settings: CrawlerSettings) -> None:
        self.settings = settings
        self._session: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp 会话。"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": self.settings.user_agent,
                    "Referer": "https://www.gamekee.com/",
                },
            )
        return self._session

    async def close(self) -> None:
        """关闭 aiohttp 会话。"""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _download_file(self, url: str, save_path: Path) -> bool:
        """下载单个文件到指定路径。"""
        if save_path.exists():
            return True

        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            session = await self._get_session()
            async with self._semaphore:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning("下载失败 [HTTP %d]: %s", response.status, url)
                        return False
                    data = await response.read()
                    save_path.write_bytes(data)
                    return True
        except asyncio.TimeoutError:
            logger.warning("下载超时: %s", url)
            return False
        except aiohttp.ClientError as e:
            logger.warning("下载请求错误: %s -> %s", url, e)
            return False
        except OSError as e:
            logger.warning("文件写入错误: %s -> %s", save_path, e)
            return False


class VoicePipeline(BasePipeline):
    """语音下载管道。"""

    async def process(self, items: list[VoiceItem], result: CrawlResult) -> None:
        """批量下载语音文件。"""
        result.total_found = len(items)

        for item in items:
            save_path = Path(item.save_path)
            if save_path.exists():
                result.skipped += 1
                continue

            url = item.audio_url
            if url.startswith("//"):
                url = "https:" + url

            success = await self._download_file(url, save_path)
            if success:
                result.downloaded += 1
            else:
                result.failed += 1
                result.errors.append(f"语音下载失败: {item.student_name}-{item.language}-{item.category}{item.title} ({url})")

            await asyncio.sleep(self.settings.download_delay)

        await self.close()


class IllustrationPipeline(BasePipeline):
    """立绘下载管道。"""

    async def process(self, items: list[IllustrationItem], result: CrawlResult) -> None:
        """批量下载立绘文件。"""
        result.total_found = len(items)

        for item in items:
            save_path = Path(item.save_path)
            if save_path.exists():
                result.skipped += 1
                continue

            url = item.image_url
            if url.startswith("//"):
                url = "https:" + url

            success = await self._download_file(url, save_path)
            if success:
                result.downloaded += 1
            else:
                result.failed += 1
                result.errors.append(f"立绘下载失败: {item.student_name}-{item.category}-{item.name} ({url})")

            await asyncio.sleep(self.settings.download_delay)

        await self.close()
