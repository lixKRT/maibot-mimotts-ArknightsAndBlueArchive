"""蔚蓝档案爬虫模块。"""

from crawlers.blue_archive_crawler.items import IllustrationItem, VoiceItem
from crawlers.blue_archive_crawler.pipelines import IllustrationPipeline, VoicePipeline
from crawlers.blue_archive_crawler.settings import CrawlerSettings

__all__ = [
    "CrawlerSettings",
    "VoiceItem",
    "IllustrationItem",
    "VoicePipeline",
    "IllustrationPipeline",
]
