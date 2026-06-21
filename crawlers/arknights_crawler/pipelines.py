"""下载管道 -- 负责将爬取的数据保存到本地文件系统。"""

import logging
from pathlib import Path

import aiohttp

from crawlers.arknights_crawler.items import IllustrationItem, OperatorInfoItem, VoiceItem

logger = logging.getLogger(__name__)


class VoicePipeline:
    """语音下载管道。"""

    def __init__(self, delay: float = 0.5) -> None:
        self._delay = delay

    async def process(
        self,
        item: VoiceItem,
        session: aiohttp.ClientSession,
        semaphore: "asyncio.Semaphore",
    ) -> bool:
        if not item.url or not item.save_path:
            logger.warning("语音项缺少 URL 或保存路径: %s", item.title)
            return False

        save_path = Path(item.save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        if save_path.exists():
            logger.debug("语音文件已存在，跳过: %s", save_path)
            return True

        async with semaphore:
            try:
                async with session.get(item.url) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, "wb") as f:
                            f.write(content)
                        logger.info("已下载语音: %s", save_path.name)
                        return True
                    else:
                        logger.warning(
                            "语音下载失败 [%d]: %s - %s",
                            response.status, item.title, item.url,
                        )
                        return False
            except aiohttp.ClientError as exc:
                logger.error("语音下载请求异常: %s - %s", item.title, exc)
                return False
            except OSError as exc:
                logger.error("语音文件写入失败: %s - %s", save_path, exc)
                return False


class TextPipeline:
    """文本保存管道。"""

    def process(self, item: OperatorInfoItem) -> bool:
        if not item.save_path:
            logger.warning("档案项缺少保存路径: %s", item.operator_name)
            return False

        save_path = Path(item.save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            text = item.to_text()
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.info("已保存档案: %s", save_path)
            return True
        except OSError as exc:
            logger.error("档案文件写入失败: %s - %s", save_path, exc)
            return False


class ImagePipeline:
    """图片下载管道。"""

    def __init__(self, delay: float = 0.5) -> None:
        self._delay = delay

    async def process(
        self,
        item: IllustrationItem,
        session: aiohttp.ClientSession,
        semaphore: "asyncio.Semaphore",
    ) -> bool:
        if not item.url or not item.save_path:
            logger.warning("立绘项缺少 URL 或保存路径: %s", item.stage)
            return False

        save_path = Path(item.save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        if save_path.exists():
            logger.debug("立绘文件已存在，跳过: %s", save_path)
            return True

        async with semaphore:
            try:
                async with session.get(item.url) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(save_path, "wb") as f:
                            f.write(content)
                        logger.info("已下载立绘: %s", save_path.name)
                        return True
                    else:
                        logger.warning(
                            "立绘下载失败 [%d]: %s - %s",
                            response.status, item.stage, item.url,
                        )
                        return False
            except aiohttp.ClientError as exc:
                logger.error("立绘下载请求异常: %s - %s", item.stage, exc)
                return False
            except OSError as exc:
                logger.error("立绘文件写入失败: %s - %s", save_path, exc)
                return False
