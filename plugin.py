"""AI Voice Service Plugin for MaiBot."""

import asyncio
import base64
import sys
from pathlib import Path
from typing import Any, Optional

# 将插件目录添加到 sys.path，确保 crawlers 模块可以被导入
_plugin_dir = str(Path(__file__).parent)
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from maibot_sdk import API, CONFIG_RELOAD_SCOPE_SELF, MaiBotPlugin, Tool, Field, PluginConfigBase
from maibot_sdk.types import ActivationType, ToolParameterInfo, ToolParamType

try:
    from .tts_service import MiMoTTSService
except ImportError:
    from tts_service import MiMoTTSService


class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "插件"
    enabled: bool = Field(default=True, description="是否启用")
    config_version: str = Field(default="1.0.0", description="配置版本")


class VoiceSectionConfig(PluginConfigBase):
    __ui_label__ = "语音设置"
    mimo_api_key: str = Field(default="", description="MiMo API Key")
    api_base_url: str = Field(
        default="https://token-plan-cn.xiaomimimo.com/v1",
        description="MiMo API地址",
        json_schema_extra={"label": "API地址"},
    )
    voice_mode: str = Field(default="clone", description="语音模式: 'clone'(音色复刻) 或 'preset'(预置音色)")
    preset_voice: str = Field(default="mimo_default", description="预置音色ID（仅preset模式生效）")
    voices_dir: str = Field(default="voices", description="音色目录路径（相对于插件目录）")
    default_voice: str = Field(default="", description="默认音色名称（clone模式下为音频文件名）")
    clone_voice: str = Field(default="", description="复刻音色文件名（clone模式下优先使用）")


class CharacterVoiceCloneConfig(PluginConfigBase):
    __ui_label__ = "角色语音克隆"
    enable_character: str = Field(default="", description="启用的角色名称（修改 voices_dir 指向）")
    character_language: str = Field(default="cn", description="启用的语言（cn/jp/kr/en），与 enable_character 共同定位 voices_dir")
    Arknights_character: str = Field(default="桃金娘，铃兰", description="明日方舟角色列表（逗号分隔）")
    BlueArchive_character: str = Field(default="爱丽丝，柯伊", description="蔚蓝档案角色列表（逗号分隔）")
    Max_Size_Synthesized_Audio: float = Field(default=2.0, description="合成音频最大文件大小（MB），范围 1-8，支持小数")


class VoicePluginConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    voice: VoiceSectionConfig = Field(default_factory=VoiceSectionConfig)
    character_voice_clone: CharacterVoiceCloneConfig = Field(default_factory=CharacterVoiceCloneConfig)


class AIVoicePlugin(MaiBotPlugin):
    config_model = VoicePluginConfig

    def __init__(self) -> None:
        super().__init__()
        self.tts_service: Optional[MiMoTTSService] = None
        self.voices: dict[str, str] = {}
        self.default_voice: str = ""
        self._updating_config: bool = False  # 防止配置更新循环

    async def on_load(self) -> None:
        self._ensure_config_exists()
        self.ctx.logger.info("AI Voice Plugin loading...")
        api_key = self.config.voice.mimo_api_key
        if not api_key:
            self.ctx.logger.warning("MiMo API Key not configured")
        self.tts_service = MiMoTTSService(api_key=api_key, api_base_url=self.config.voice.api_base_url, logger=self.ctx.logger)
        self.default_voice = self.config.voice.default_voice or self.config.voice.clone_voice

        # 检查角色语音克隆配置
        await self._check_character_voices()

        # 重新获取 default_voice（可能被 _check_character_voices 修改）
        self.default_voice = self.config.voice.default_voice or self.config.voice.clone_voice

        await self._load_voices()
        self.ctx.logger.info("AI Voice Plugin loaded: mode=%s, default_voice=%s, voices=%s",
            self.config.voice.voice_mode, self.default_voice, list(self.voices.keys()))

    def _ensure_config_exists(self) -> None:
        """如果用户目录下不存在 config.toml，则从 config.example.toml 复制生成。不会覆盖用户已有配置。"""
        import shutil
        plugin_dir = Path(__file__).parent
        config_path = plugin_dir / "config.toml"
        example_path = plugin_dir / "config.example.toml"
        if config_path.exists():
            return
        if example_path.exists():
            shutil.copy2(example_path, config_path)
            self.ctx.logger.info("Generated config.toml from config.example.toml")
        else:
            self.ctx.logger.warning("Neither config.toml nor config.example.toml found")

    async def on_unload(self) -> None:
        if self.tts_service:
            await self.tts_service.close()
            self.tts_service = None
        self.voices.clear()

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            # 防止配置更新循环
            if self._updating_config:
                self.ctx.logger.debug("跳过配置更新（正在修改中）")
                return
            self.ctx.logger.info("Plugin config updated: version=%s", version)
            if self.tts_service and self.config.voice.mimo_api_key:
                self.tts_service.update_api_key(self.config.voice.mimo_api_key)
                self.tts_service.update_api_base_url(self.config.voice.api_base_url)

            # 检查角色语音克隆配置
            await self._check_character_voices()

            # 重新获取 default_voice（可能被 _check_character_voices 修改）
            self.default_voice = self.config.voice.default_voice or self.config.voice.clone_voice

            # 检查合成音频是否需要裁剪
            cvc = self.config.character_voice_clone
            if cvc.enable_character:
                plugin_dir = Path(__file__).parent
                voices_dir = plugin_dir / "voices"
                lang = cvc.character_language
                if lang not in ["cn", "jp", "kr", "en"]:
                    lang = "cn"

                # 检查对应语言目录的合成音频
                synth_path = voices_dir / cvc.enable_character / "voice" / lang / "Synthetic_Audio.mp3"
                if synth_path.exists():
                    max_size_bytes = int(cvc.Max_Size_Synthesized_Audio * 1024 * 1024)
                    if synth_path.stat().st_size > max_size_bytes:
                        self.ctx.logger.info("配置变更：裁剪合成音频至 %.1fMB", cvc.Max_Size_Synthesized_Audio)
                        await self._trim_audio(synth_path, max_size_bytes)

            await self._load_voices()
            self.ctx.logger.info("Config reloaded: mode=%s, default_voice=%s", self.config.voice.voice_mode, self.default_voice)

    async def _check_character_voices(self) -> None:
        """检查角色语音克隆配置，必要时启动爬虫。"""
        cvc = self.config.character_voice_clone
        plugin_dir = Path(__file__).parent
        # 始终使用基础 voices 目录，而不是当前的 voices_dir（可能已被修改）
        voices_dir = plugin_dir / "voices"

        # 解析角色列表
        arknights_chars = [c.strip() for c in cvc.Arknights_character.replace("，", ",").split(",") if c.strip()]
        ba_chars = [c.strip() for c in cvc.BlueArchive_character.replace("，", ",").split(",") if c.strip()]

        # 检查并爬取明日方舟角色
        for char_name in arknights_chars:
            char_dir = voices_dir / char_name
            if not self._has_audio_files(char_dir):
                self.ctx.logger.info("角色「%s」无音频资源，启动明日方舟爬虫...", char_name)
                result = await self._crawl_arknights_voice(char_name, str(voices_dir))
                if result.get("success"):
                    self.ctx.logger.info("角色「%s」爬取成功: %d 个语音", char_name, result.get("voice_count", 0))
                else:
                    self.ctx.logger.warning("角色「%s」爬取失败: %s", char_name, result.get("error", "未知错误"))

        # 检查并爬取蔚蓝档案角色
        for char_name in ba_chars:
            char_dir = voices_dir / char_name
            if not self._has_audio_files(char_dir):
                self.ctx.logger.info("角色「%s」无音频资源，启动蔚蓝档案爬虫...", char_name)
                result = await self._crawl_blue_archive_voice(char_name, str(voices_dir))
                if result.get("success"):
                    self.ctx.logger.info("角色「%s」爬取成功: %d 个语音", char_name, result.get("voice_count", 0))
                else:
                    self.ctx.logger.warning("角色「%s」爬取失败: %s", char_name, result.get("error", "未知错误"))

        # 如果 enable_character 不为空，为每个语言文件夹合成音频
        if cvc.enable_character:
            enable_dir = voices_dir / cvc.enable_character
            if enable_dir.exists() and self._has_audio_files(enable_dir):
                # 为每个语言文件夹生成合成音频
                voice_dir = enable_dir / "voice"
                if voice_dir.exists():
                    for lang_dir in voice_dir.iterdir():
                        if lang_dir.is_dir() and lang_dir.name in ["cn", "jp", "kr", "en"]:
                            await self._synthesize_audio(lang_dir, cvc.Max_Size_Synthesized_Audio)

                # 根据 character_language 设置 voices_dir
                lang = cvc.character_language
                if lang not in ["cn", "jp", "kr", "en"]:
                    lang = "cn"  # 默认中文
                target_dir = voice_dir / lang

                # 如果配置的语言目录不存在，查找可用的语言目录
                if not target_dir.exists():
                    available_langs = [d.name for d in voice_dir.iterdir() if d.is_dir() and d.name in ["cn", "jp", "kr", "en"]]
                    if available_langs:
                        lang = available_langs[0]
                        target_dir = voice_dir / lang
                        self.ctx.logger.warning("语言目录「%s」不存在，已切换到: %s", cvc.character_language, lang)
                    else:
                        self.ctx.logger.error("角色「%s」没有可用的语言资源，尝试重新爬取...", cvc.enable_character)
                        await self._retry_crawl(cvc.enable_character, voices_dir)
                        return

                self.config.voice.voices_dir = f"voices/{cvc.enable_character}/voice/{lang}"
                self.config.voice.default_voice = "Synthetic_Audio"
                self._update_config_file(voices_dir=f"voices/{cvc.enable_character}/voice/{lang}", default_voice="Synthetic_Audio")
                self.ctx.logger.info("voices_dir 已修改为: %s, default_voice: Synthetic_Audio", self.config.voice.voices_dir)
            else:
                # 角色目录不存在或为空，尝试爬取
                self.ctx.logger.warning("角色「%s」的音频目录不存在或为空，尝试爬取...", cvc.enable_character)
                await self._retry_crawl(cvc.enable_character, voices_dir)
        else:
            # enable_character 为空时，恢复默认值
            self.config.voice.voices_dir = "voices"
            self.config.voice.default_voice = ""
            self._update_config_file(voices_dir="voices", default_voice="")

    async def _retry_crawl(self, character_name: str, voices_dir: Path) -> None:
        """尝试重新爬取角色资源。

        Args:
            character_name: 角色名称
            voices_dir: voices 目录路径
        """
        cvc = self.config.character_voice_clone

        # 判断是哪个游戏的角色
        arknights_chars = [c.strip() for c in cvc.Arknights_character.replace("，", ",").split(",") if c.strip()]
        ba_chars = [c.strip() for c in cvc.BlueArchive_character.replace("，", ",").split(",") if c.strip()]

        if character_name in arknights_chars:
            self.ctx.logger.info("重新爬取明日方舟角色「%s」...", character_name)
            result = await self._crawl_arknights_voice(character_name, str(voices_dir))
            if result.get("success"):
                self.ctx.logger.info("角色「%s」重新爬取成功: %d 个语音", character_name, result.get("voice_count", 0))
            else:
                self.ctx.logger.error("角色「%s」重新爬取失败: %s", character_name, result.get("error", "未知错误"))
        elif character_name in ba_chars:
            self.ctx.logger.info("重新爬取蔚蓝档案角色「%s」...", character_name)
            result = await self._crawl_blue_archive_voice(character_name, str(voices_dir))
            if result.get("success"):
                self.ctx.logger.info("角色「%s」重新爬取成功: %d 个语音", character_name, result.get("voice_count", 0))
            else:
                self.ctx.logger.error("角色「%s」重新爬取失败: %s", character_name, result.get("error", "未知错误"))
        else:
            self.ctx.logger.error("角色「%s」不在已配置的角色列表中", character_name)

    def _update_config_file(self, voices_dir: str = None, default_voice: str = None) -> None:
        """直接修改 config.toml 文件中的配置。

        Args:
            voices_dir: 新的 voices_dir 值
            default_voice: 新的 default_voice 值
        """
        import toml

        plugin_dir = Path(__file__).parent
        config_path = plugin_dir / "config.toml"

        if not config_path.exists():
            return

        # 设置标志防止循环
        self._updating_config = True

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = toml.load(f)

            # 确保 voice section 存在
            if "voice" not in config:
                config["voice"] = {}

            if voices_dir is not None:
                config["voice"]["voices_dir"] = voices_dir
            if default_voice is not None:
                config["voice"]["default_voice"] = default_voice

            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(config, f)

            self.ctx.logger.info("config.toml 已更新: voices_dir=%s, default_voice=%s", voices_dir, default_voice)
        except Exception as e:
            self.ctx.logger.error("更新 config.toml 失败: %s", e)
        finally:
            # 延迟重置标志，给文件监控时间处理
            asyncio.get_event_loop().call_later(1.0, self._reset_config_flag)

    def _reset_config_flag(self) -> None:
        """重置配置更新标志。"""
        self._updating_config = False

    async def _synthesize_audio(self, char_dir: Path, max_size_mb: float) -> None:
        """将角色目录下的所有音频合成为一个 MP3 文件。

        如果已存在合成音频且超出限制，则裁剪至符合要求。

        Args:
            char_dir: 角色音频目录（如 voices/桃金娘/voice/jp）
            max_size_mb: 最大文件大小（MB），支持小数
        """
        try:
            from pydub import AudioSegment
        except ImportError:
            self.ctx.logger.error("pydub 未安装，无法合成音频。请执行: pip install pydub")
            return

        # 限制大小范围 1-8MB
        max_size_mb = max(1.0, min(8.0, max_size_mb))
        max_size_bytes = int(max_size_mb * 1024 * 1024)
        # 允许实际大小与目标的差值在 1MB 以内
        min_size_bytes = int(max(0, max_size_mb - 1.0) * 1024 * 1024)
        # MP3 128kbps: 字节 = 毫秒 * 128000 / 8 / 1000 = 毫秒 * 16
        max_duration_ms = int(max_size_bytes / 16)
        min_duration_ms = int(min_size_bytes / 16)

        output_path = char_dir / "Synthetic_Audio.mp3"

        # 检查已存在的合成音频是否符合要求
        if output_path.exists():
            existing_size = output_path.stat().st_size
            if existing_size <= max_size_bytes:
                self.ctx.logger.info("合成音频已存在且符合要求: %s (%.2fMB)", output_path, existing_size / 1024 / 1024)
                return
            else:
                # 裁剪已存在的合成音频
                self.ctx.logger.info("合成音频超出限制 (%.2fMB > %.2fMB)，裁剪中...", existing_size / 1024 / 1024, max_size_mb)
                await self._trim_audio(output_path, max_size_bytes)
                return

        # 收集所有音频文件（按文件名排序）
        audio_files = []
        for ext in ['*.wav', '*.mp3', '*.ogg']:
            audio_files.extend(char_dir.glob(ext))
        # 排除已有的合成音频
        audio_files = [f for f in audio_files if f.name != 'Synthetic_Audio.mp3']
        audio_files.sort(key=lambda f: f.name)

        if not audio_files:
            self.ctx.logger.warning("未找到音频文件: %s", char_dir)
            return

        self.ctx.logger.info("开始合成音频: %d 个文件，最大限制 %.1fMB", len(audio_files), max_size_mb)

        # 合成音频（后面的优先，所以从后往前合并）
        combined = AudioSegment.empty()
        used_files = []

        # 从后往前遍历（后面的音频更优先）
        for audio_file in reversed(audio_files):
            try:
                segment = AudioSegment.from_file(audio_file)
                # 检查合并后时长是否超出上限
                if len(combined) + len(segment) > max_duration_ms:
                    # 如果当前时长已在允许范围内（距上限差值 <= 1MB），停止添加
                    if len(combined) >= min_duration_ms:
                        break
                    # 如果当前时长不足最小值，继续添加（允许略微超过上限）
                    # 但不能超过太多（最多再加一个片段）

                combined = segment + combined  # 插入到前面（保持后面的优先）
                used_files.append(audio_file.name)
            except Exception as e:
                self.ctx.logger.warning("加载音频失败: %s - %s", audio_file.name, e)

        if len(combined) == 0:
            self.ctx.logger.error("合成失败：无有效音频")
            return

        # 导出为 MP3
        combined.export(output_path, format='mp3', bitrate='128k')

        file_size = output_path.stat().st_size
        self.ctx.logger.info("合成完成: %s (%.2fMB，使用 %d 个文件)", output_path, file_size / 1024 / 1024, len(used_files))

    async def _trim_audio(self, audio_path: Path, max_size_bytes: int) -> None:
        """裁剪音频文件至指定大小。

        从后往前保留音频内容（后面的优先），截断前面的部分。

        Args:
            audio_path: 音频文件路径
            max_size_bytes: 最大字节数
        """
        try:
            from pydub import AudioSegment
        except ImportError:
            self.ctx.logger.error("pydub 未安装，无法裁剪音频")
            return

        try:
            audio = AudioSegment.from_file(audio_path)
            original_size = audio_path.stat().st_size

            # 计算目标时长（毫秒）
            # 字节 = 毫秒 * 比特率 / 8 / 1000
            # 比特率 128kbps = 128000 bps
            target_ms = int(max_size_bytes * 8 * 1000 / 128000)

            if len(audio) <= target_ms:
                self.ctx.logger.info("音频时长未超限，无需裁剪")
                return

            # 从后往前截取（保留后面的音频）
            trimmed = audio[-target_ms:]

            # 导出裁剪后的音频
            trimmed.export(audio_path, format='mp3', bitrate='128k')

            new_size = audio_path.stat().st_size
            self.ctx.logger.info("裁剪完成: %.2fMB -> %.2fMB", original_size / 1024 / 1024, new_size / 1024 / 1024)
        except Exception as e:
            self.ctx.logger.error("裁剪音频失败: %s - %s", audio_path, e)
        """检查角色语音克隆配置，必要时启动爬虫。"""
        cvc = self.config.character_voice_clone
        plugin_dir = Path(__file__).parent
        voices_dir = plugin_dir / self.config.voice.voices_dir

        # 解析角色列表
        arknights_chars = [c.strip() for c in cvc.Arknights_character.replace("，", ",").split(",") if c.strip()]
        ba_chars = [c.strip() for c in cvc.BlueArchive_character.replace("，", ",").split(",") if c.strip()]

        # 检查并爬取明日方舟角色
        for char_name in arknights_chars:
            char_dir = voices_dir / char_name
            if not self._has_audio_files(char_dir):
                self.ctx.logger.info("角色「%s」无音频资源，启动明日方舟爬虫...", char_name)
                result = await self._crawl_arknights_voice(char_name, str(voices_dir))
                if result.get("success"):
                    self.ctx.logger.info("角色「%s」爬取成功: %d 个语音", char_name, result.get("voice_count", 0))
                else:
                    self.ctx.logger.warning("角色「%s」爬取失败: %s", char_name, result.get("error", "未知错误"))

        # 检查并爬取蔚蓝档案角色
        for char_name in ba_chars:
            char_dir = voices_dir / char_name
            if not self._has_audio_files(char_dir):
                self.ctx.logger.info("角色「%s」无音频资源，启动蔚蓝档案爬虫...", char_name)
                result = await self._crawl_blue_archive_voice(char_name, str(voices_dir))
                if result.get("success"):
                    self.ctx.logger.info("角色「%s」爬取成功: %d 个语音", char_name, result.get("voice_count", 0))
                else:
                    self.ctx.logger.warning("角色「%s」爬取失败: %s", char_name, result.get("error", "未知错误"))

        # 如果 enable_character 不为空，修改 voices_dir
        if cvc.enable_character:
            enable_dir = voices_dir / cvc.enable_character
            if enable_dir.exists() and self._has_audio_files(enable_dir):
                self.config.voice.voices_dir = f"voices/{cvc.enable_character}"
                self.ctx.logger.info("voices_dir 已修改为: %s", self.config.voice.voices_dir)
            else:
                self.ctx.logger.warning("enable_character「%s」的音频目录不存在或为空", cvc.enable_character)

    def _has_audio_files(self, directory: Path) -> bool:
        """检查目录是否有音频文件（递归检查子目录）。"""
        if not directory.exists():
            return False
        audio_files = list(directory.rglob("*.wav")) + list(directory.rglob("*.mp3")) + list(directory.rglob("*.ogg"))
        return len(audio_files) > 0

    async def _crawl_arknights_voice(self, character_name: str, output_dir: str) -> dict:
        """启动明日方舟语音爬虫。"""
        try:
            from crawlers.arknights_crawler.settings import CrawlerSettings
            from crawlers.arknights_crawler.spiders.voice_spider import VoiceSpider

            settings = CrawlerSettings(output_dir=output_dir)
            spider = VoiceSpider(settings)
            return await spider.run(operator_name=character_name, output_dir=output_dir)
        except Exception as e:
            self.ctx.logger.error("明日方舟爬虫异常: %s", e)
            return {"success": False, "error": str(e)}

    async def _crawl_blue_archive_voice(self, character_name: str, output_dir: str) -> dict:
        """启动蔚蓝档案语音爬虫。"""
        try:
            from crawlers.blue_archive_crawler.settings import CrawlerSettings
            from crawlers.blue_archive_crawler.spiders.voice_spider import VoiceSpider

            settings = CrawlerSettings(output_dir=output_dir)
            # 加载学生映射
            crawler_dir = Path(__file__).parent / "crawlers" / "blue_archive_crawler"
            settings.load_student_mapping(crawler_dir)

            student_id = settings.find_student_id(character_name)
            if not student_id:
                return {"success": False, "error": f"未找到学生「{character_name}」的ID，请在 mapping.json 中添加映射（访问 https://www.gamekee.com/ba 查找学生ID）"}

            spider = VoiceSpider(settings)
            result = await spider.crawl(
                student_name=character_name,
                student_id=student_id,
                output_dir=output_dir,
            )
            return {
                "success": result.failed == 0 and result.downloaded > 0,
                "voice_count": result.downloaded,
                "save_path": f"{output_dir}/{character_name}",
                "error": "; ".join(result.errors[:3]) if result.errors else "",
            }
        except Exception as e:
            self.ctx.logger.error("蔚蓝档案爬虫异常: %s", e)
            return {"success": False, "error": str(e)}

    async def _load_voices(self) -> None:
        voices_dir_str = self.config.voice.voices_dir
        plugin_dir = Path(__file__).parent
        voices_dir = plugin_dir / voices_dir_str
        self.ctx.logger.info("Loading voices from: %s (plugin_dir=%s)", voices_dir, plugin_dir)

        if not voices_dir.exists():
            self.ctx.logger.warning("Voices dir not found: %s, creating it", voices_dir)
            voices_dir.mkdir(parents=True, exist_ok=True)
            return

        self.ctx.logger.info("Voices dir exists: %s, contents: %s", voices_dir, [f.name for f in voices_dir.iterdir()])

        audio_files = list(voices_dir.glob("*.wav")) + list(voices_dir.glob("*.mp3")) + list(voices_dir.glob("*.ogg"))
        if not audio_files:
            self.ctx.logger.warning("No audio files found in: %s", voices_dir)
            return

        self.voices.clear()
        for audio_file in audio_files:
            voice_name = audio_file.stem
            file_size = audio_file.stat().st_size
            # Detect MIME type from extension
            suffix = audio_file.suffix.lower()
            mime_type = "audio/wav" if suffix == ".wav" else "audio/mpeg"
            with open(audio_file, "rb") as f:
                audio_bytes = f.read()
            b64_data = base64.b64encode(audio_bytes).decode("ascii")
            # Store with MIME type prefix for API call
            self.voices[voice_name] = f"data:{mime_type};base64,{b64_data}"
            self.ctx.logger.info("Loaded voice: %s, raw=%dKB, b64=%dKB, mime=%s", voice_name, file_size // 1024, len(b64_data) // 1024, mime_type)

        if not self.default_voice and self.voices:
            self.default_voice = next(iter(self.voices))
            self.ctx.logger.info("Using default voice: %s", self.default_voice)

        self.ctx.logger.info("Voice loading complete, total %d voices, names=%s", len(self.voices), list(self.voices.keys()))

    async def _find_stream_id(self, kwargs: dict) -> str:
        """Find stream_id from various sources."""
        # Method 1: from kwargs (system may pass it)
        sid = kwargs.get("stream_id", "")
        if sid:
            self.ctx.logger.info("Got stream_id from kwargs: %s", sid)
            return str(sid)

        # Method 2: from kwargs message
        msg = kwargs.get("message", {})
        if isinstance(msg, dict):
            sid = msg.get("stream_id", "")
            if sid:
                self.ctx.logger.info("Got stream_id from message: %s", sid)
                return str(sid)

        # Method 3: try to find group stream
        try:
            streams = await self.ctx.chat.get_group_streams()
            if streams:
                sid = streams[0].get("stream_id", "")
                self.ctx.logger.info("Using first group stream: %s", sid)
                return str(sid)
        except Exception as e:
            self.ctx.logger.warning("chat.get_group_streams failed: %s", e)

        return ""

    async def _send_voice(self, audio_b64: str, stream_id: str) -> bool:
        """Send voice message using base64 format.
        注意: 调用后 audio_b64 会被消费，不再可用。
        """
        self.ctx.logger.info("Sending voice to stream=%s, b64_len=%d", stream_id, len(audio_b64))

        b64_url = f"base64://{audio_b64}"
        # 原始引用可以释放（如果调用方已 del 则无额外效果，但作为安全措施）
        audio_b64 = ""

        # Method 1: record type with base64 (NapCat standard for voice)
        try:
            await self.ctx.send.custom("record", {"file": b64_url}, stream_id)
            self.ctx.logger.info("Sent via record+base64")
            return True
        except Exception as e:
            self.ctx.logger.warning("record+base64 failed: %s", e)

        # Method 2: voice type with base64
        try:
            await self.ctx.send.custom("voice", {"file": b64_url}, stream_id)
            self.ctx.logger.info("Sent via voice+base64")
            return True
        except Exception as e:
            self.ctx.logger.warning("voice+base64 failed: %s", e)

        self.ctx.logger.error("All voice send methods failed")
        return False

    def _resolve_voice(self, voice_name: str) -> tuple[str, str, str]:
        """解析音色名称，返回 (voice_key, audio_base64, mode)。
        mode: 'clone' 使用音色复刻, 'preset' 使用预置音色。
        """
        voice_mode = self.config.voice.voice_mode

        # 确定要使用的音色 key
        voice_key = voice_name if voice_name and voice_name != "default" else self.default_voice

        # clone 模式：从本地音频文件中查找参考音频
        if voice_mode == "clone":
            if voice_key and voice_key in self.voices:
                return voice_key, self.voices[voice_key], "clone"

            # clone_voice 配置兜底
            clone_fallback = self.config.voice.clone_voice
            if clone_fallback and clone_fallback in self.voices:
                self.ctx.logger.warning("Voice '%s' not found, using clone_voice config: '%s'", voice_key, clone_fallback)
                return clone_fallback, self.voices[clone_fallback], "clone"

            # 如果 voices 非空但指定的没有，报错而非静默切换
            if self.voices:
                available = list(self.voices.keys())
                self.ctx.logger.error("Voice '%s' not found in voices! Available: %s. "
                    "请在 config.toml 的 clone_voice 或 default_voice 中指定一个已有的音色名。", voice_key, available)
                return "", "", ""

            self.ctx.logger.error("No voices loaded! Please put .wav/.mp3 files in the voices/ directory.")
            return "", "", ""

        # preset 模式
        preset_id = voice_key or self.config.voice.preset_voice or "mimo_default"
        return preset_id, "", "preset"

    @API("voice_clone_tts", description="TTS with specified voice", version="1", public=True)
    async def voice_clone_tts(self, text: str, style_instruction: str = "", stream_id: str = "", voice_name: str = "") -> dict[str, Any]:
        if not self.tts_service:
            return {"success": False, "error": "TTS service not initialized"}

        if not text or not text.strip():
            return {"success": False, "error": "Empty text"}

        voice_key, ref_audio, mode = self._resolve_voice(voice_name)
        if not voice_key:
            return {"success": False, "error": "No voice configured. Check voice config."}

        self.ctx.logger.info("TTS request: mode=%s, voice_key=%s, text_len=%d, style_len=%d",
            mode, voice_key, len(text), len(style_instruction))

        try:
            if mode == "clone":
                result = await self.tts_service.synthesize_with_voice_clone(
                    text=text, reference_audio_base64=ref_audio, style_instruction=style_instruction,
                )
            else:
                result = await self.tts_service.synthesize_with_preset(
                    text=text, voice_id=voice_key, style_instruction=style_instruction,
                )

            # 释放参考音频引用
            ref_audio = ""

            success = result.get("success")
            error = result.get("error", "")
            audio_b64 = result.get("audio_base64", "")
            self.ctx.logger.info("TTS result: success=%s, audio_len=%d, error=%s", success, len(audio_b64), error)

            if success and audio_b64 and stream_id:
                # 提取纯 base64 数据
                if "base64," in audio_b64:
                    audio_b64 = audio_b64.split("base64,", 1)[1]
                    audio_b64 = audio_b64.strip()

                # 立即从 result 中移除大字段，避免双重内存占用
                result.pop("audio_base64", None)

                await self._send_voice(audio_b64, stream_id)
                audio_b64 = ""
            elif audio_b64:
                # 不需要发送时也清理
                result.pop("audio_base64", None)

            return result
        except Exception as e:
            self.ctx.logger.error("TTS failed: %s", e)
            return {"success": False, "error": str(e)}

    @Tool(
        "send_voice_reply",
        brief_description="使用语音回复用户，可选传入风格指令控制语气情绪",
        detailed_description=(
            "使用语音进行回复。当用户要求语音、用户发送了语音消息、或你认为当前场景适合语音回复时调用。\n"
            "必填参数：reply_text（回复文本）、msg_id（当前消息ID）。\n"
            "可选参数：style_instruction（语音风格指令），不传则使用默认音色自然朗读，需要更生动的表达时可填写。\n\n"
            "【风格控制】可通过 style_instruction 参数精细控制语音演绎效果，"
            "根据你当前扮演的角色人设和对话情境，主动提供完整的风格描述，让语音更拟人、更有感染力。\n\n"
            "支持三种风格控制方式，可自由组合：\n\n"
            "1. 自然语言风格指令（推荐）：用自然语言描述语气、情绪、语速等，像给演员说戏一样。\n"
            "   示例：'一位温柔的少女，声音清甜软糯，语速偏慢，用安慰的语气，带点关切'\n"
            "   示例：'语气俏皮活泼，带点小得意，语速偏快，声音明亮有活力'\n"
            "   示例：'声音低沉严肃，像在教训人，语速慢一些，带点长辈的威严'\n\n"
            "2. 导演模式（高级）：从角色、场景、指导三个维度全方位刻画表演，适合需要高度拟人化的场景。\n"
            "   示例：'角色：一位温柔的大姐姐，性格体贴温暖，声音甜美有亲和力。"
            "场景：安慰失恋的朋友。指导：语调柔和温暖，气息松弛，偶尔带叹息，语速偏慢，尾音上扬带笑意。'\n"
            "   示例：'角色：百年门阀的大小姐，声音冷冽有威压，说话语速极慢，每个字都像在舌尖滚过。"
            "场景：在祠堂面对企图带她私奔的男人。指导：实音重且硬，尾音处加入轻微气音透出疲惫。'\n\n"
            "3. 音频标签（在 reply_text 中使用）：在文本任意位置用括号标注语气/情绪/声音动作。\n"
            "   中文全角/半角均可：（紧张）呼……冷静。（叹气）算了。（轻笑）好吧好吧。\n"
            "   英文：(sighs) I don't know. (laughs) That's funny!\n"
            "   整段风格标签：在文本开头加（温柔）你好呀~ 或（东北话）哎呀妈呀~ 或（唱歌）歌词...\n"
            "   常用风格标签：开心/悲伤/愤怒/温柔/慵懒/俏皮/磁性/沙哑/甜美/冷漠/严肃/活泼/深沉 等\n"
            "   常用动作标签：叹气/轻笑/哽咽/深呼吸/咳嗽/打哈欠/低语/提高音量 等\n\n"
            "提示：style_instruction（整体风格）+ reply_text 中的音频标签（句内细节）可同时使用，两者不冲突。"
        ),
        activation_type=ActivationType.ALWAYS,
        parameters=[
            ToolParameterInfo(name="reply_text", param_type=ToolParamType.STRING, description="回复文本。可在文本中插入音频标签控制句内语气细节，如（叹气）（轻笑）（温柔）（紧张）等。", required=True),
            ToolParameterInfo(name="msg_id", param_type=ToolParamType.STRING, description="当前消息ID", required=True),
            ToolParameterInfo(
                name="style_instruction",
                param_type=ToolParamType.STRING,
                description=(
                    "（可选）语音风格指令，用自然语言描述语气、情绪、语速等，让语音更拟人。\n"
                    "不传则默认朗读。当你觉得需要更生动的表达时再填写。\n"
                    "简单用法：'温柔安慰的语气，语速稍慢'\n"
                    "导演模式：'角色：XX，性格XX。场景：XX。指导：语调XX，语速XX，气息XX。'\n"
                    "也可配合 reply_text 中的音频标签（叹气/轻笑/停顿等）使用。"
                ),
                required=False,
                default="",
            ),
        ],
    )
    async def send_voice_reply(self, reply_text: str, msg_id: str = "", style_instruction: str = "", **kwargs: Any) -> dict[str, Any]:
        # Find the correct stream_id
        stream_id = await self._find_stream_id(kwargs)
        if not stream_id:
            self.ctx.logger.error("Cannot find stream_id for msg_id=%s, kwargs_keys=%s", msg_id, list(kwargs.keys()))
            return {"success": False, "method": "voice", "error": "Cannot find chat stream"}

        self.ctx.logger.info("Using stream_id=%s for voice reply, text_len=%d", stream_id, len(reply_text))

        # Always use the configured default voice
        asyncio.create_task(self._async_voice_reply(reply_text, style_instruction, stream_id, ""))
        return {"success": True, "method": "voice", "error": ""}

    async def _async_voice_reply(self, text: str, style_instruction: str, stream_id: str, voice_name: str) -> None:
        """Send voice reply asynchronously."""
        try:
            result = await self.voice_clone_tts(text=text, style_instruction=style_instruction, stream_id=stream_id, voice_name=voice_name)
            self.ctx.logger.info("Async voice reply result: %s", result.get("success"))
        except Exception as e:
            self.ctx.logger.error("Async voice reply failed: %s", e)


def create_plugin() -> AIVoicePlugin:
    return AIVoicePlugin()