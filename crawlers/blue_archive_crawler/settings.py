"""爬虫配置管理。"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CrawlerSettings:
    """爬虫运行配置。"""

    output_dir: str = "voices"
    request_timeout: int = 30
    download_delay: float = 0.5
    max_concurrent: int = 4
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    mapping_file: str = "mapping.json"
    max_synthesized_audio_mb: float = 8.0  # 合成音频最大文件大小（MB）

    # 缓存的学生映射数据
    _student_mapping: dict[str, str] = field(default_factory=dict, repr=False)

    def load_student_mapping(self, crawler_dir: Path) -> dict[str, str]:
        """加载学生 ID 映射表。"""
        if self._student_mapping:
            return self._student_mapping

        mapping_path = crawler_dir / self.mapping_file
        try:
            with open(mapping_path, encoding="utf-8") as f:
                data = json.load(f)
                # 支持两种格式：直接映射或嵌套在 students 中
                if "students" in data:
                    self._student_mapping = data["students"]
                else:
                    self._student_mapping = data
        except FileNotFoundError:
            self._student_mapping = {}
        except Exception:
            self._student_mapping = {}

        return self._student_mapping

    def find_student_id(self, student_name: str) -> str | None:
        """根据名称查找学生 ID。"""
        if not student_name:
            return None
        return self._student_mapping.get(student_name)
