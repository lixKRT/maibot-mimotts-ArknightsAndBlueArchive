# MiMo TTS Arknights And BlueArchive Voice Plugin for MaiBot

基于小米 MiMo-V2.5-TTS 的 AI 语音服务插件，为 MaiBot 提供智能语音回复功能。支持**预置音色**和**音色复刻**两种模式。

> **本 Fork 新增功能**（对比原版 [Emilia-awa/maibot-mimotts-voice](https://github.com/Emilia-awa/maibot-mimotts-voice)）
>
> - 🎮 **游戏语音克隆**：自动爬取蔚蓝档案（Gamekee）和明日方舟（PRTS Wiki）角色语音
> - 🎵 **合成音频**：将多个音频合成为一个 MP3 文件，支持大小限制（1-8MB）
> - 📝 **台词台本**：自动生成角色语音台本（Markdown 格式）
> - 🌐 **多语言支持**：支持 cn/jp/kr/en 四种语言
> - ⚙️ **角色语音克隆配置**：新增 `[character_voice_clone]` 配置段，支持自动爬取和音频合成

详细说明见 [角色语音克隆](#角色语音克隆) 章节。

---

## 功能特性(好用的话请点个star⭐~)

- 🎤 **预置音色**：内置 9 种精品音色（中文/英文，男声/女声），开箱即用
- 🎭 **音色复刻**：通过音频样本精准复刻任意音色，放入 `voices/` 目录即可
- 🤖 **AI 工具链暴露**：`send_voice_reply` 工具暴露在 AI 工具链中（`activation_type=ALWAYS`），AI 可自主决定何时使用语音回复
- 🎨 **AI 智能风格控制**：风格指令由 AI 根据角色人设和对话情境自行决定，无需用户手动配置
- 🎬 **导演模式**：支持从角色、场景、指导三个维度全方位刻画语音表演，AI 自动判断何时需要深度演绎
- ⚡ **异步发送**：语音合成和发送异步执行，不阻塞 AI 主循环
- 🔧 **自动配置初始化**：首次启动时自动从 `config.example.toml` 生成 `config.toml`，不覆盖用户已有配置

## 安装

### 1. 复制插件到 MaiBot

```bash
cd /path/to/MaiBot/plugins/
git clone https://github.com/lixKRT/maibot-mimotts-ArknightsAndBlueArchive.git
```

### 2. 安装依赖

```bash
pip install aiohttp selectolax pydub
```

**注意**：`pydub` 需要 `ffmpeg` 支持。请确保系统已安装 ffmpeg：

```bash
# Windows (winget)
winget install ffmpeg

# Linux
apt install ffmpeg

# macOS
brew install ffmpeg
```

### 3. 配置

编辑 `config.toml`（可从 `config.example.toml` 复制）：

```toml
[plugin]
enabled = true
config_version = "1.0.0"

[voice]
mimo_api_key = "your_api_key_here"
api_base_url = "https://token-plan-cn.xiaomimimo.com/v1"
voice_mode = "clone"
voices_dir = "voices"

[character_voice_clone]
enable_character = "柯伊"
character_language = "cn"
Arknights_character = "桃金娘，铃兰"
BlueArchive_character = "爱丽丝，柯伊"
Max_Size_Synthesized_Audio = 2.0
```

### 4. 重启 MaiBot

插件会自动加载。

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `mimo_api_key` | MiMo API Key（必填） | - |
| `api_base_url` | API 地址 | `https://token-plan-cn.xiaomimimo.com/v1` |
| `voice_mode` | 音色模式：`preset` 或 `clone` | `preset` |
| `preset_voice` | 预置音色名称（preset 模式） | `mimo_default` |
| `voices_dir` | 音色复刻目录（clone 模式，相对于插件目录） | `voices` |
| `clone_voice` | 指定复刻音色文件名（留空使用第一个文件） | - |

### API 地址

| 用户类型 | 地址 |
|---------|------|
| Plan 用户（包月/套餐） | `https://token-plan-cn.xiaomimimo.com/v1` |
| 按量计费用户 | `https://api.xiaomimimo.com/v1` |

## 音色模式

### 预置音色（preset）

无需额外配置，直接在 `preset_voice` 中填入音色名称：

| 音色名 | 语言 | 性别 |
|--------|------|------|
| `mimo_default` | 中文 | 女性（冰糖） |
| `冰糖` | 中文 | 女性 |
| `茉莉` | 中文 | 女性 |
| `苏打` | 中文 | 男性 |
| `白桦` | 中文 | 男性 |
| `Mia` | 英文 | 女性 |
| `Chloe` | 英文 | 女性 |
| `Milo` | 英文 | 男性 |
| `Dean` | 英文 | 男性 |

### 音色复刻（clone）

1. 将 `voice_mode` 改为 `clone`
2. 将参考音频文件放入 `voices/` 目录（支持 WAV 和 MP3）
3. 文件名即为音色名称，建议录音时长 30 秒以上

```
plugins/maibot-mimotts-voice/voices/
└── salt.wav    # 音色名称: salt
```

## 工具说明

插件提供 `send_voice_reply` 工具给 AI，AI 会根据对话上下文自行判断是否调用。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `reply_text` | string | ✅ | 要合成语音的回复文本 |
| `msg_id` | string | ✅ | 当前消息 ID，用于自动查找聊天流 |
| `style_instruction` | string | ❌ | 语音风格指令 |

### 风格控制方式

风格控制由 AI 根据当前扮演的角色人设和对话情境**自行决定**，无需用户手动指定。AI 会自动判断何时需要风格指令，并选择合适的表达方式。

支持三种风格控制方式，AI 可自由组合使用：

**1. 自然语言风格指令**（AI 通过 `style_instruction` 参数传入）

AI 用自然语言描述语气、情绪、语速等，像给演员说戏一样：

- `一位温柔的少女，声音清甜软糯，语速偏慢，用安慰的语气`
- `语气俏皮活泼，带点小得意，语速偏快`
- `声音低沉严肃，像在教训人，语速慢一些`

**2. 导演模式**（AI 根据场景需要自动启用）

AI 从角色、场景、指导三个维度全方位刻画表演：

```
角色：一位温柔的大姐姐，性格体贴温暖，声音甜美有亲和力。
场景：安慰失恋的朋友。
指导：语调柔和温暖，气息松弛，偶尔带叹息，语速偏慢，尾音上扬带笑意。
```

**3. 音频标签**（AI 在 `reply_text` 中自动插入）

AI 在文本任意位置用括号标注语气/情绪/声音动作：

- 中文：`（紧张）呼……冷静。（叹气）算了。（轻笑）好吧好吧。`
- 英文：`(sighs) I don't know. (laughs) That's funny!`
- 整段风格：`（温柔）你好呀~` `（东北话）哎呀妈呀~` `（唱歌）歌词...`
- 常用标签：开心/悲伤/愤怒/温柔/慵懒/俏皮/磁性/沙哑/甜美/冷漠/叹气/轻笑/哽咽/深呼吸 等

> `style_instruction`（整体风格）+ `reply_text` 中的音频标签（句内细节）可同时使用，两者不冲突。

## 目录结构

```
maibot-mimotts-voice/
├── plugin.py           # 插件主入口
├── tts_service.py      # MiMo TTS 服务封装
├── config.toml         # 插件配置（gitignored）
├── config.example.toml # 配置示例
├── _manifest.json      # 插件清单
├── README.md           # 本文档
├── LICENSE             # MIT 许可证
├── .gitignore          # Git 忽略规则
├── requirements.txt    # Python 依赖
└── voices/             # 音色复刻文件目录（gitignored）
```

## 角色语音克隆

本 Fork 新增的角色语音克隆功能，支持自动爬取蔚蓝档案和明日方舟的角色语音。

### 配置说明

在 `config.toml` 中添加 `[character_voice_clone]` 配置段：

```toml
[character_voice_clone]
enable_character = "柯伊"                # 启用的角色名称
character_language = "cn"                # 启用的语言（cn/jp/kr/en）
Arknights_character = "桃金娘，铃兰"      # 明日方舟角色列表（逗号分隔）
BlueArchive_character = "爱丽丝，柯伊"    # 蔚蓝档案角色列表（逗号分隔）
Max_Size_Synthesized_Audio = 2.0         # 合成音频最大文件大小（MB），1-8
```

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `enable_character` | 启用的角色名称，修改 `voices_dir` 指向 | `柯伊` |
| `character_language` | 启用的语言（cn/jp/kr/en） | `cn` |
| `Arknights_character` | 明日方舟角色列表（逗号分隔） | `桃金娘，铃兰` |
| `BlueArchive_character` | 蔚蓝档案角色列表（逗号分隔） | `爱丽丝，柯伊` |
| `Max_Size_Synthesized_Audio` | 合成音频最大文件大小（MB），范围 1-8 | `2.0` |

### 使用方法

1. 在 `config.toml` 中配置角色列表
2. 设置 `enable_character` 为要使用的角色名称
3. 设置 `character_language` 为要使用的语言
4. 插件启动时会自动：
   - 检查角色是否有音频资源
   - 如果没有，自动启动爬虫爬取
   - 为每个语言文件夹生成合成音频（`Synthetic_Audio.mp3`）
   - 设置 `voices_dir` 指向对应语言文件夹

### 合成音频

- 将多个音频文件合成为一个 MP3 文件
- 文件大小受 `Max_Size_Synthesized_Audio` 控制
- 后面的音频优先（按文件名排序 1→10, a→z）
- 允许实际大小与目标的差值在 1MB 以内
- 配置变更时自动裁剪超限文件

### 台词台本

爬取语音时自动生成台词台本（`script.md`），格式：

```markdown
# 桃金娘 语音台本

# cn_001 - 任命助理
**中文**: 博士，我来找你玩啦~
**日语**: やっほードクター、遊びに来たよー。

# cn_002 - 交谈1
**中文**: 博士，你可不要小看我...
**日语**: ドクター、小さいからって甘く見ないでね！...
```

### 支持的游戏

| 游戏 | 数据源 | 支持语言 |
|------|--------|----------|
| 明日方舟 | PRTS Wiki | cn, jp, kr, en |
| 蔚蓝档案 | Gamekee | jp, kr, cn |

### 目录结构

```
voices/
├── 桃金娘/
│   ├── script.md        # 台词台本
│   └── voice/
│       ├── cn/
│       │   ├── cn_001.wav
│       │   ├── cn_002.wav
│       │   └── Synthetic_Audio.mp3  # 合成音频
│       └── jp/
│           ├── jp_001.wav
│           └── Synthetic_Audio.mp3
└── 爱丽丝/
    ├── script.md
    └── voice/
        ├── jp/
        │   └── Synthetic_Audio.mp3
        └── kr/
            └── Synthetic_Audio.mp3
```

### 依赖

- `aiohttp` - HTTP 客户端
- `selectolax` - HTML 解析（明日方舟爬虫）
- `pydub` - 音频合成
- `ffmpeg` - 音频格式转换（pydub 依赖）

### 注意事项

1. **ffmpeg**：合成音频功能需要 ffmpeg 支持，请确保已安装
2. **映射文件**：蔚蓝档案学生映射已内置 267 个学生，如需添加新学生请参考 [蔚蓝档案学生ID获取](#蔚蓝档案学生id获取) 章节
3. **括号兼容**：角色名称支持全角/半角括号自动转换（如 `爱丽丝（女仆）` 和 `爱丽丝(女仆)` 都能识别）

---

## 蔚蓝档案学生ID获取

蔚蓝档案爬虫需要学生 ID 才能获取语音数据。ID 映射文件位于 `crawlers/blue_archive_crawler/mapping.json`，已内置 267 个学生。

### 如何获取新学生的 ID

1. 访问 [Gamekee 蔚蓝档案学生图鉴](https://www.gamekee.com/ba/tj)
2. 找到目标学生，点击进入学生页面
3. 从 URL 中提取 ID：`https://www.gamekee.com/ba/tj/72904.html` 中的 `72904` 就是学生 ID

### 添加新学生到映射

编辑 `crawlers/blue_archive_crawler/mapping.json`，在 `students` 对象中添加：

```json
{
  "students": {
    "爱丽丝": "72904",
    "柯伊": "690582",
    "新学生名称": "学生ID"
  }
}
```

### 已内置的学生（部分）

| 学生名称 | ID |
|---------|-----|
| 爱丽丝 | 72904 |
| 柯伊 | 690582 |
| 日奈 | 59934 |
| 星野 | 46680 |
| 白子 | 46677 |
| ... | ... |

完整列表请查看 `crawlers/blue_archive_crawler/mapping.json`（共 267 个学生）。

---

## 更新日志

### v2.0.0 (Fork)

本版本基于原版 [Emilia-awa/maibot-mimotts-voice](https://github.com/Emilia-awa/maibot-mimotts-voice) v1.6.0 修改。

**新增功能：**
- 🎮 **游戏语音克隆**：自动爬取蔚蓝档案（Gamekee）和明日方舟（PRTS Wiki）角色语音
- 🎵 **合成音频**：将多个音频合成为一个 MP3，支持大小限制（1-8MB）
- 📝 **台词台本**：自动生成角色语音台本（Markdown 格式）
- 🌐 **多语言支持**：支持 cn/jp/kr/en 四种语言
- ⚙️ **角色语音克隆配置**：新增 `[character_voice_clone]` 配置段

**新增依赖：**
- `selectolax` - HTML 解析（明日方舟爬虫）
- `pydub` - 音频合成
- `ffmpeg` - 音频格式转换（pydub 依赖）

**新增文件：**
- `crawlers/` - 爬虫模块目录
  - `arknights_crawler/` - 明日方舟爬虫
  - `blue_archive_crawler/` - 蔚蓝档案爬虫
- `.claude/rules/` - Claude Code 开发规则
- `.gitignore` - Git 忽略规则

**修改文件：**
- `plugin.py` - 添加角色语音克隆功能、合成音频逻辑、爬虫调度
- `config.example.toml` - 新增 `[character_voice_clone]` 配置段
- `_manifest.json` - 添加新依赖声明
- `requirements.txt` - 添加新依赖
- `README.md` - 添加新功能文档

**未修改的原版核心逻辑：**
- TTS 服务 (`tts_service.py`) - 完全保留
- 预置音色功能 - 完全保留
- 音色复刻功能 - 完全保留
- AI 工具链 (`send_voice_reply`) - 完全保留
- 风格控制功能 - 完全保留

### v1.6.0

- 🔧 **工具链暴露**：`send_voice_reply` 工具暴露在 AI 工具链中，AI 可自主决定何时使用语音回复
- 🎬 **AI 智能风格控制**：风格指令由 AI 根据角色人设和对话情境自行决定，支持自然语言指令、导演模式、音频标签三种方式
- 🎨 **style_instruction 可选化**：AI 自行判断何时需要风格指令，无需每次填写
- 📋 **配置自动初始化**：首次启动自动从 `config.example.toml` 生成 `config.toml`

### v1.0.0

- 初始版本：预置音色、音色复刻、基础语音回复功能

## 注意事项

1. **API Key**：需要在 [小米 MiMo 平台](https://platform.xiaomimimo.com) 申请
2. **音色复刻**：建议录音时长不低于 30 秒，确保无背景噪音
3. **Base64 大小**：音色参考音频的 Base64 编码不能超过 10MB
4. **费用**：MiMo-V2.5-TTS 系列当前限时免费
5. **ffmpeg**：合成音频功能需要 ffmpeg 支持，请确保已安装
6. **映射文件**：蔚蓝档案学生映射已内置 267 个学生，明日方舟干员映射需要手动添加到 `crawlers/arknights_crawler/mapping.json`

## 许可证

MIT License
