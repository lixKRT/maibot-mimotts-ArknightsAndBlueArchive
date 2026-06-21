"""数据项定义。"""

from dataclasses import dataclass, field


@dataclass
class VoiceItem:
    """语音数据项。"""

    student_name: str = ""
    language: str = ""
    category: str = ""
    title: str = ""
    audio_url: str = ""
    save_path: str = ""


@dataclass
class IllustrationItem:
    """立绘数据项。"""

    student_name: str = ""
    category: str = ""
    name: str = ""
    image_url: str = ""
    save_path: str = ""


@dataclass
class CrawlResult:
    """爬取结果汇总。"""

    student_name: str = ""
    total_found: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """生成人类可读的结果摘要。"""
        parts = [f"学生「{self.student_name}」"]
        parts.append(f"发现 {self.total_found} 项资源")
        parts.append(f"下载 {self.downloaded} 项")
        if self.skipped > 0:
            parts.append(f"跳过 {self.skipped} 项（已存在）")
        if self.failed > 0:
            parts.append(f"失败 {self.failed} 项")
        result = "，".join(parts) + "。"
        if self.errors:
            result += "\n失败详情：\n" + "\n".join(f"  - {e}" for e in self.errors[:10])
            if len(self.errors) > 10:
                result += f"\n  ...等共 {len(self.errors)} 个错误"
        return result
