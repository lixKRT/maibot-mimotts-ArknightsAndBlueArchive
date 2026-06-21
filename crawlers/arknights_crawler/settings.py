"""爬虫配置管理。"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CrawlerSettings:
    """爬虫运行配置。"""

    output_dir: str = "voices"
    request_timeout: int = 30
    download_delay: float = 0.5
    max_concurrent: int = 4
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    max_synthesized_audio_mb: float = 2.0  # 合成音频最大文件大小（MB）

    # PRTS Wiki 相关 URL
    wiki_base_url: str = "https://prts.wiki"
    audio_base_url: str = "https://torappu.prts.wiki/assets/audio"
    media_base_url: str = "https://media.prts.wiki"

    def get_voice_url(self, language: str, operator_id: str, number: str) -> str:
        """构造语音下载 URL。"""
        lang_path_map = {
            "cn": "voice_cn",
            "jp": "voice",
            "kr": "voice_kr",
            "en": "voice_en",
        }
        lang_path = lang_path_map.get(language, "voice_cn")
        return f"{self.audio_base_url}/{lang_path}/{operator_id}/cn_{number}.wav"

    def get_operator_url(self, operator_name: str) -> str:
        """构造干员页面 URL。"""
        return f"{self.wiki_base_url}/w/{operator_name}"

    def get_voice_page_url(self, operator_name: str) -> str:
        """构造干员语音记录页面 URL。"""
        return f"{self.wiki_base_url}/w/{operator_name}/语音记录"

    def get_image_url(self, filename: str, md5_hash: str) -> str:
        """构造立绘图片 URL（基于 MD5 哈希）。"""
        from urllib.parse import quote
        encoded_filename = quote(filename)
        return f"{self.media_base_url}/{md5_hash[0]}/{md5_hash[:2]}/{encoded_filename}"
