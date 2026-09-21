# ingest2md — 把你看到和听到的内容变成 LLM 可读 Markdown

[![CI](https://github.com/leecolin2023/ingest2md/actions/workflows/ci.yml/badge.svg)](https://github.com/leecolin2023/ingest2md/actions/workflows/ci.yml)

`ingest2md` 是一个轻量的多来源内容采集工具。输入网页链接、App 分享文案或本地音视频，它尽可能提取正文、回答、图片信息或音视频转写，并整理成**人能直接阅读、后续能批量交给大模型处理的本地 Markdown**。

设计原则：

> **输入端尽量强，输出端尽量简单；抓得丰富，存得轻。**

默认只生成 Markdown。只有图片需要本地化时才附带 `images/`；JSON、SRT、TXT、媒体副本和切片都必须显式请求。

v0.8 的音视频原则进一步收紧为：**字幕优先，本地转写默认可用，云端模型按需增强；没有任何付费 API，也应该能完成完整 ingestion。**

## v0.9.1：Long-lived Runtime

批量执行开始复用真正昂贵的运行资源，但 Adapter 仍只负责单项内容：

- 新增 `RuntimeContext`，单条与 batch 共用同一执行资源抽象；
- 同一批次只创建一个 ASR backend；
- `SenseVoiceBackend` 缓存已加载的 ONNX 模型，同一批次多个媒体不再重复初始化模型；
- 新增 `BrowserRuntime`，知乎 / 小红书 / 抖音 / Generic Web fallback 复用同一个 Chromium 进程；
- 每个网页任务仍创建独立 BrowserContext，并在任务结束后关闭，避免 Cookie/页面状态串任务；
- Runtime 与 SQLite TaskStore 完全分离：Runtime 管执行资源，Batch 管任务状态；
- 当前仍保持串行批量；并发和资源 semaphore 留到后续真实 benchmark 再决定。

整体关系：

```text
single ─┐
        ├─ IngestionEngine ─ RuntimeContext ─ Router ─ Extractor
batch ──┘                    ├─ shared ASR backend / SenseVoice model
                             └─ shared Chromium / isolated contexts
```

## v0.9.0：Batch Foundation

批量能力成为独立于平台的核心调度层，而不是某个平台 Adapter 的循环：

- 新增 `IngestionEngine`，单条 CLI 与批量模式都调用同一个 `ingest_one()`；
- 新增 `ingest2md batch <manifest>`，支持 TXT / JSONL / CSV；
- SQLite 保存任务状态，支持 `--resume`、`--take`、`--retry-failed`；
- 输入阶段按规范化引用去重，并记录抓取后的 `source_type + source_id` canonical key；
- 配置指纹变化会产生新的任务版本；成功任务输出缺失时可在 resume 时重新进入 pending；
- v0.9.0 故意保持串行，不引入 worker/pipeline 框架。

示例：

```bash
ingest2md batch sources.txt --config config.yaml -o output/batch --resume
ingest2md batch sources.csv -o output/batch --take 20
ingest2md batch sources.jsonl -o output/batch --resume --retry-failed
```

JSONL 任务保持轻量：

```json
{"source":"https://v.douyin.com/xxx/","name":"AI视频01","tags":["AI","抖音"]}
{"source":"BV1xxxxxxxxx","name":"B站课程"}
{"source":"./meeting.mp4","name":"会议录像"}
```

## v0.8.4：抖音单视频浏览器采集

本版把抖音从“仅识别”升级为轻量可用的单视频 Adapter，但仍不维护私有签名：

- 支持 `v.douyin.com` 分享短链和 `douyin.com` 单视频页面；
- 使用现有 Playwright 打开真实页面并执行平台自身 JavaScript；
- 优先读取浏览器已生成签名的详情响应中的音视频地址，回退到 DOM 暴露的直接 `http(s)` 地址；
- 可选加载 Netscape 格式抖音 Cookie；
- 逐个下载候选媒体并校验音轨和时长，避免把页面占位动画交给 ASR；
- 校验通过后复用现有 ASR backend，默认 SenseVoice 本地转写；
- 如果页面只暴露 `blob:`、登录墙或没有直接媒体地址，会明确提示 Cookie / 本地文件 fallback；
- 不实现 `a_bogus` / `X-Bogus`，也不主动调用抖音私有详情 API；只读取真实浏览器会话已经产生的详情响应。仍不接 DouK Sidecar、主页/合集/评论/直播或“无水印”保证。

## v0.8.3：SenseVoice 本地性能优化

本版只优化本地 SenseVoice 链路，不改变字幕优先、ASR backend 或 Markdown 输出结构：

- SenseVoice 默认切片由 20 秒调整为 **30 秒**；
- 默认批量推理由 batch=1 调整为 **batch=2**，并真正以文件列表批量调用模型；
- 音频切片从“每段启动一次 ffmpeg”改为 **单次 ffmpeg segment**；
- 新增 `--sensevoice-batch-size`，便于本机测试 batch=2 / 4；
- 日志增加预处理、模型准备、推理、总耗时、model calls、realtime speed 与 RTF；
- `local-asr` 补充 `onnxscript`，降低首次 ONNX 导出阶段缺依赖失败的概率。

默认值选择更稳妥的 `30s / batch=2`；内存和 CPU 余量较大的机器可显式尝试 `batch=4`。

## v0.8.2：Maintenance cleanup

本版不新增功能、不改变用户行为，只收敛容易产生双重维护的内部实现：

- 本地媒体与网络媒体统一使用 `retain_media()`；
- Netscape Cookie 只保留一套底层 parser，浏览器与 YouTube 诊断分别做轻量适配；
- Extractor registry 同时负责顺序与 Settings 注入，CLI 不再维护一份平台类型名单；
- YouTube 音频访问诊断函数改名为 `probe_playback_access()`，避免被误当作普通 metadata probe；
- 浏览器 User-Agent 统一为一个常量；
- HTML meta 读取统一到 `htmlutils.meta_content()`。

## v0.8.1：YouTube 获取链路修复

- 正常 YouTube ingestion **不再前置调用 `probe_playback_access()`**；`probe_video` 只保留给 `--check-access`。
- 先直接探测人工/自动字幕；有字幕时复用同一次 yt-dlp `info` 作为标题、频道、时长等元数据，不再额外做音频播放 probe。
- YouTube 字幕探测与音频下载复用同一套 Cookie、重试和 JS runtime 配置。
- 没有可用字幕时才进入音频下载 → ASR fallback。
- 这能减少项目自身的重复 YouTube 请求，但无法替代 YouTube 对 Cookie、网络出口或 PO Token 的外部校验。

## v0.8：Local-first transcription

1. **默认本地 ASR**：没有平台字幕时，默认使用 `SenseVoiceBackend`（SenseVoiceSmall ONNX）在本地 CPU 转写。
2. **Backend 自己决定音频预处理**：SenseVoice 使用约 20 秒、16kHz 单声道 PCM WAV；OpenAI-compatible ASR 使用较长 MP3；LLM audio 保留原来的多模态音频切片方式。
3. **删除强制中文翻译**：字幕和 ASR 结果按原语言直接进入 `TranscriptResult → Markdown`。YouTube/B站存在字幕时可以做到 0 ASR、0 LLM、0 API 成本。
4. **保留两种高级云端入口**：`openai` 调用 OpenAI-compatible `/audio/transcriptions`；`llm` 调用兼容 `chat/responses + input_audio` 的多模态模型。Opencode 只是 `llm` backend 的默认示例配置，不再是项目必需依赖。

> **字幕优先，本地转写默认可用，云端模型按需增强；没有任何付费 API，也应该能完成完整 ingestion。**

## v0.7：把现有能力变聪明

1. **YouTube / Bilibili 字幕优先**：优先使用平台人工字幕，其次自动字幕；只有没有可用字幕时才下载音频进入 ASR。
2. **Generic Web 使用 Trafilatura**：HTTP 获取后优先交给 Trafilatura 抽取主正文，正文不足时才使用现有浏览器渲染；旧轻量解析保留为兜底。
3. **PDF / DOCX / PPTX / XLSX**：新增 Document Adapter，识别后委托 Microsoft MarkItDown；通过 `ingest2md[documents]` 按需安装，不自行实现文档解析。
4. **`--explain`**：只解释输入类型、识别来源、Adapter 和处理计划，不抓取、不下载、不调用模型，也不生成文件。

## v0.6 工程重命名

- 项目、Python distribution、Python package、CLI 和文档统一从旧名称重命名为 `ingest2md`。
- 不保留旧包名或旧 CLI 兼容层，避免后续迭代长期维护双命名。
- 内容抓取与转写能力保持不变。

## v0.6 新增

1. **小宇宙 Podcast**：单集页面 → 节目简介 / Show Notes → 公开音频 → 原语言转写 → 中文翻译 → 一个 Markdown。
2. **本地音视频**：支持常见音频、视频文件直接进入现有转写链路。
3. **Content Reference 输入**：CLI 输入从单纯 URL 扩展为 URL、App 分享文案中的 URL、本地文件、B站 BV 号。
4. **抖音 / 微信视频号明确识别**：v0.6 起不会掉进 Generic Web；v0.8.4 抖音单视频已升级为浏览器轻量采集，视频号仍保持 deferred。

## 支持内容

| 来源 | 状态 | 默认采集语义 | 默认输出 |
|---|---|---|---|
| 微信公众号 | ✅ | 单篇文章 | Markdown + `images/` |
| 知乎 | ✅ | **一个问题 + 尽可能多的回答** | 单个 Markdown |
| 小红书 | ✅ 轻量 | 单篇笔记正文 + 可取得图片 | Markdown + `images/`（有图片时） |
| Bilibili | ✅ | 单视频/分P → 字幕优先 → 本地 ASR fallback → 原语言 | 单个 Markdown |
| YouTube | ✅ | 单视频 → 字幕优先 → 本地 ASR fallback → 原语言 | 单个 Markdown |
| **小宇宙** | **✅ v0.6** | Show Notes + 播客转写 | 单个 Markdown |
| **本地音视频** | **✅ v0.8 Local-first** | 本地媒体 → 默认 SenseVoice 本地转写 → 原语言 | 单个 Markdown |
| 普通网页 | ✅ | 主要正文 | 单个 Markdown |
| 抖音 | ✅ 轻量 | 单视频/分享短链 → 浏览器详情响应/DOM 媒体地址 → ASR | 单个 Markdown |
| 微信视频号 | ⏸ | 自动识别；媒体下载暂缓 | 明确提示改走本地文件 |

知乎问题 URL 和某个回答 URL 都会按“问题导向”处理：定位到所属问题，把当前可获取的回答尽量收进同一个 Markdown。

## 安装

Python 3.10+：

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install -e .
python -m playwright install chromium
```

微信首次使用还需要：

```bash
python -m camoufox fetch
```

基础安装仍保持轻量。需要本地音视频转写时安装：

```bash
python -m pip install -e ".[local-asr]"
```

`local-asr` 会安装 `funasr-onnx + onnxruntime + modelscope + funasr + onnxscript`。第一次真正使用 SenseVoice 时会自动下载/定位 `iic/SenseVoiceSmall`；如目录中尚无 ONNX，`funasr-onnx` 可借助 FunASR 完成首次导出。也可以通过 `sensevoice_model_dir` 指向已经准备好的本地 ONNX 模型目录。音视频 ASR 仍需要系统可用的 `ffmpeg` / `ffprobe`。

YouTube 建议安装当前版 Deno 或 Node.js；遇到登录/机器人校验时提供 Cookie。

文档能力按需安装，不进入默认依赖：

```bash
python -m pip install -e ".[documents]"
```

## 输入已经不是只有 URL

当前把输入统一为：

```text
Content Reference
= URL
| 分享文案中的 URL
| 本地媒体路径
| 本地 PDF / DOCX / PPTX / XLSX
| BV号
```

下面这些都可以直接使用：

```bash
# 普通 URL
ingest2md "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e"

# 整段 App 分享文本：会提取第一条 http(s) URL
ingest2md "6.48 复制打开抖音，看看某个作品 https://v.douyin.com/akR8LCIaTMI/ 其他分享口令"

# 本地音频
ingest2md "./podcast.m4a"

# 本地视频
ingest2md "D:\Downloads\douyin.mp4"

# 本地文档（需安装 documents extra）
ingest2md "./report.pdf"

# B站 BV 号
ingest2md "BV1xx411c7mD"

# 快速测试前一分钟
ingest2md "./video.mp4" --limit-seconds 60
```

### 本地媒体格式

音频：`.mp3 .m4a .wav .aac .flac .ogg .opus`

视频：`.mp4 .mkv .mov .webm .avi .m4v`

只有**真实存在的文件**才会被判定为本地媒体。像 `missing.mp4` 这样的不存在路径不会误进入 Local Media。

## 最常用命令

```bash
# 微信
ingest2md "https://mp.weixin.qq.com/s/xxxx" -o archive

# 知乎：默认按问题抓尽可能多回答
ingest2md "https://www.zhihu.com/question/2083802170001044893" -o archive

# 只想快速抓前 10 个回答
ingest2md "https://www.zhihu.com/question/2083802170001044893" --max-answers 10 -o archive

# 小红书
ingest2md "https://www.xiaohongshu.com/explore/xxxx" -o archive

# 普通网页
ingest2md "https://example.com/article" -o archive

# 抖音单视频 / 分享短链
ingest2md "https://v.douyin.com/xxxx/" -o archive

# B站 / YouTube：有字幕直接使用；无字幕默认本地 SenseVoice
# Bilibili 仍按平台字幕优先处理

小宇宙 / 本地音视频：默认本地 SenseVoice
ingest2md "https://www.bilibili.com/video/BVxxxxxxxxxx" -o archive
ingest2md "https://www.youtube.com/watch?v=xxxxxxxxxxx" -o archive
ingest2md "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e" -o archive
ingest2md "./meeting.mp3" -o archive
```

## 抖音单视频：浏览器轻量采集

支持：

```text
v.douyin.com/<share>
douyin.com/video/<id>
整段抖音分享文案中的第一条 URL
```

默认流程：

```text
分享文案 / 抖音 URL
 ↓
Router → DouyinExtractor
 ↓
Playwright 打开真实页面并跟随短链跳转
 ↓
读取浏览器已生成签名的详情响应
 ↓
回退读取 video.currentSrc / video.src / source[src]
 ↓
得到音视频候选地址并逐个下载
 ↓
用 ffprobe 校验音轨和时长
 ↓
复用 transcribe_audio()
 ↓
Markdown
```

匿名公开页面优先直接尝试；如果页面需要登录，可提供：

```bash
ingest2md "<抖音URL>" --douyin-cookies-file douyin-cookies.txt
```

实现不自行生成平台签名，只消费真实浏览器会话已经取得的详情响应和 DOM 地址。如果浏览器详情响应不可用、页面只提供 `blob:` 或出现登录墙，会明确失败并建议：

1. 更新/提供抖音登录 Cookie；
2. 或手动下载视频后执行 `ingest2md "/path/to/douyin.mp4"`。

项目**不自行实现** `a_bogus` / `X-Bogus` 签名，也不主动构造抖音私有详情 API 请求；只消费真实浏览器会话已经取得的详情响应。不提供 DouK Sidecar、主页批量、合集、评论、直播或无水印承诺。

## 微信视频号：仍只识别来源

视频号仍在 Generic Web 前被识别，但当前不自动获取媒体：

```text
weixin.qq.com/sph/
channels.weixin.qq.com
```

程序会明确提示下载视频后走本地媒体通道，不会生成一个只有页面壳的 Markdown。

## 小宇宙处理方式

小宇宙单集只接入公开页面，不依赖私有登录 API。解析顺序：

```text
公开 episode 页面
 ↓
优先读取 __NEXT_DATA__ 中的 episode 数据
 ↓
失败则读取 og:title / og:description / og:audio
 ↓
音频 URL 再提供 media.xyzcdn.net 正则兜底
 ↓
HTTP 流式下载到临时目录
 ↓
复用现有 transcribe_audio()
 ↓
Show Notes + 原语言转写 → 一个 Markdown
```

最终 Markdown 形态：

```markdown
# Vol.1 AI最前沿的人已经不聊大模型了

> **来源**: 小宇宙
> **播客**: 易论AI
> **时长**: 1小时33分钟
> 原文链接: https://www.xiaoyuzhoufm.com/episode/...

---

## 节目简介

……

## Show Notes

- 01:21 AI落地……
- 15:16 ……

## 转写正文

### 00:00–05:00

……

### 05:00–10:00

……
```

默认不会留下 `episode.json`、`raw.html`、下载音频或切片；这些都只在明确请求附加产物时保留。

## 本地音视频处理方式

v0.8 不再让一个统一的 300 秒切片规则绑住所有 ASR。流程变成：

```text
本地文件 / 已下载媒体
 ↓
ASR backend
 ├─ sensevoice（默认）→ 30秒 16k mono PCM WAV → batch=2 SenseVoiceSmall ONNX
 ├─ openai           → 较长 MP3 → /audio/transcriptions
 └─ llm              → MP3 → chat/responses + input_audio
 ↓
原语言 TranscriptResult
 ↓
Markdown
```

视频文件仍由 ffmpeg 忽略画面，只处理音轨。不同 backend 自己决定切片大小和编码格式。

`--keep-audio` 对网络视频/播客保留下载音频；对本地媒体保存一份 `source_media.<ext>` 副本。`--keep-chunks` 保留 backend 实际使用的切片，因此 SenseVoice 通常是 WAV，云端 backend 通常是 MP3。

## `--explain`：只解释路由，不执行

```bash
ingest2md "https://www.youtube.com/watch?v=VIDEO_ID" --explain
```

会显示输入类型、规范化结果、识别来源、Adapter 和处理计划。该模式不会抓取内容、下载媒体、调用模型或生成 Markdown，适合用户和 Agent 在真正执行前确认路由。

## 输出规则：默认只有一个主 Markdown

文本型内容默认直接落在输出根目录：

```text
archive/
├── 如何评价某问题__2083802170001044893.md
├── 某篇普通网页文章.md
├── 某个YouTube视频__VIDEO_ID.md
└── 本地会议录音.md
```

如果内容带本地图片、你要求保留媒体/切片，或者显式要求附加格式，则相关文件收进一个目录：

```text
archive/
└── 某个内容/
    ├── 某个内容.md
    ├── document.json       # 仅 --formats md,json
    ├── transcript.srt      # 仅 --formats md,srt 且有转写
    ├── source_media.mp4    # 本地媒体 + --keep-audio
    └── chunks/             # 仅 --keep-chunks
```

## 额外格式全部 opt-in

默认：

```text
formats: [md]
```

需要时才指定：

```bash
ingest2md "<video-or-podcast>" --formats md,srt
ingest2md "<url>" --formats md,json
ingest2md "<url>" --formats md,txt
ingest2md "./video.mp4" --keep-audio --keep-chunks
```

支持 `md,txt,srt,json`。`srt` 只在存在转写结果时输出。

## 知乎实现策略

知乎当前网页/API 对匿名自动化访问并不稳定。项目继续采用 v0.4 的轻量策略：真实浏览器打开问题页、展开回答、持续滚动、按回答 ID 去重，多轮不再新增后停止。

优点是实现简单、与页面阅读行为接近、不需要维护私有 API 签名；代价是**不承诺抓全**。需要登录时，用 `--zhihu-cookies-file` 提供 Netscape Cookie。

## 小红书当前边界

小红书仍是“轻量可用版”：抓页面可见正文、下载当前能定位到的笔记图片，默认不调用 OCR / Vision；小红书视频暂不自动转写。

## 普通网页

普通网页先用 HTTP 获取，再由 **Trafilatura** 提取主正文；如果结果为空则使用现有轻量 HTML 解析兜底。如果正文仍明显不足或 HTTP 获取失败，才退回 Playwright 浏览器渲染后再次抽取。`ingest2md` 不自行建设更重的 crawler/browser 基础设施。

Generic Web 永远排在更具体的平台之后。当前路由优先级大致为：

```text
已识别但暂缓的平台（视频号）
→ 本地媒体
→ 抖音 / 微信 / B站 / YouTube / 小宇宙 / 知乎 / 小红书
→ Generic Web
```

## 视频 / 播客转写

v0.8 的统一逻辑：

```text
YouTube
  ↓
直接字幕探测（不前置 audio probe）
  ↓
人工字幕
  ↓没有
自动字幕
  ↓没有
下载音频
  ↓
配置 ASR backend（默认 SenseVoice 本地）
  ↓
原语言 Markdown

小宇宙 / 本地音视频
  ↓
配置 ASR backend（默认 SenseVoice 本地）
  ↓
原语言 Markdown
```

字幕路径不再需要 API Key；ASR 也不再自动进入翻译阶段。云端 backend 只有用户明确配置时才使用。

Markdown 默认按切段时间组织：

```markdown
### 00:00–05:00
……

### 05:00–10:00
……
```

## Cookie

YouTube 登录、**登录 Cookie 获取步骤**、Cookie 校验、JS Runtime 与 403/PO Token 的详细诊断见 [`YOUTUBE_LOGIN.md`](YOUTUBE_LOGIN.md)。

Cookie 统一使用 Netscape 格式：

```bash
ingest2md "<知乎URL>" --zhihu-cookies-file zhihu-cookies.txt
ingest2md "<小红书URL>" --xiaohongshu-cookies-file xhs-cookies.txt
ingest2md "<YouTubeURL>" --youtube-cookies-file youtube-cookies.txt
ingest2md "<抖音URL>" --douyin-cookies-file douyin-cookies.txt
```

## 配置

复制 `config.example.yaml` 为 `config.yaml`。优先级：

```text
CLI 显式参数 > 对应环境变量 > config.yaml > 默认值
```

核心参数：

| 参数 | 默认 |
|---|---|
| `-o / --output` | `./output` |
| `--formats` | `md` |
| `--max-answers` | `0`，知乎尽可能多 |
| `--asr-backend` | `sensevoice` |
| `--asr-language` | `auto` |
| `--sensevoice-chunk-seconds` | `30`（允许 5–30） |
| `--sensevoice-batch-size` | `2`（内存和 CPU 余量较大时可尝试 `4`） |
| `--limit-seconds` | `0`，完整媒体 |
| `--keep-audio` | `false` |
| `--keep-chunks` | `false` |

## 代码结构

```text
ingest2md/
├── cli.py
├── config.py
├── model.py
├── router.py
├── urlutils.py                 # Content Reference 规范化 / 分享文案 URL 提取
├── browser.py
├── htmlutils.py
├── extractors/
│   ├── base.py
│   ├── deferred_media.py      # 微信视频号识别但暂缓
│   ├── douyin.py              # 抖音单视频浏览器采集
│   ├── local_media.py         # NEW
│   ├── xiaoyuzhou.py          # NEW
│   ├── wechat.py
│   ├── zhihu.py
│   ├── xiaohongshu.py
│   ├── web.py
│   ├── bilibili.py
│   ├── youtube.py
│   └── video.py
├── media/
│   ├── audio.py
│   ├── bilibili.py
│   ├── youtube.py
│   ├── douyin.py              # 抖音 DOM 媒体解析
│   └── download.py            # 通用 HTTP 流式下载
└── transcription/
    ├── service.py              # 只负责选择 backend
    ├── sensevoice.py           # 默认本地 SenseVoice ONNX
    ├── openai_asr.py           # /audio/transcriptions
    ├── llm_audio.py            # chat/responses + input_audio
    ├── subtitles.py
    └── writers.py
```

核心仍然保持简单：

```text
输入
 ↓
URL / 分享文案 / 本地路径 / BV 号规范化
 ↓
Router
 ↓
平台 Extractor
 ↓
Document
 ↓
Markdown Writer
```

没有引入 `MediaProviderManager`、Resolver Registry、manifest 或新的媒体抽象层。

## 工程状态

- Python `>=3.10`；依赖、构建方式和 `ingest2md` 命令入口统一维护在 `pyproject.toml`。
- 本地测试使用 `pytest`；当前回归测试见 `tests/`。
- GitHub Actions 会在 push 到 `main` 和 Pull Request 时，使用 Python 3.10 / 3.12 执行安装、编译检查、测试和 CLI smoke test。
- CI 不下载 Playwright 浏览器或真实媒体，也不调用转写 API；这些属于在线端到端能力，不放进基础工程 CI。

## 测试

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

v0.8 当前在原有覆盖上新增 Local-first ASR 回归，重点覆盖：

- 分享文案提取第一条 URL；
- 普通 URL 与 BV 号兼容；
- 本地媒体存在/不存在路径判定；
- 抖音分享链接在 Generic Web 前进入 DouyinExtractor；微信视频号仍被 deferred；
- 小宇宙路由、`__NEXT_DATA__`、`og:audio` 回退；
- 小宇宙调用现有 `transcribe_audio()`；
- 默认只输出 Markdown；
- opt-in JSON；
- Generic Web 正文与 Trafilatura 优先；
- PDF/DOCX/PPTX/XLSX 文档路由与 MarkItDown 委托；
- `--explain` dry-run 路由说明；
- YouTube/B站字幕优先且字幕存在时跳过 ASR；
- YouTube 无字幕时 ASR fallback；
- 默认 ASR backend 为 SenseVoice；
- `sensevoice / openai / llm` 三种 backend 路由；
- SenseVoice backend 自己生成 30 秒 WAV 切片，并按 batch 批量推理；
- OpenAI-compatible backend 自己生成 MP3 切片并调用 `/audio/transcriptions`；
- 字幕路径保持原语言，不再调用 Translator；
- v0.7 旧配置自动映射到新的 LLM backend 字段；
- 视频时间段标题；
- Netscape Cookie 解析。

详细结果见 `TEST_REPORT.md`。

> 注意：你这次提供的 v0.4 ZIP 中没有上一版测试目录，因此无法逐文件执行“原来的 9 个测试”。本轮没有删除或重构原有微信、知乎、小红书、B站、YouTube实现，并新增了针对其关键公共行为的回归测试。

## 已知限制

- 知乎、小红书可能因登录态、反爬、页面结构调整而少抓或失败；项目目标是“快速可用”，不是保证全量。
- 小宇宙依赖公开 episode 页面中可取得的音频 URL；如果平台未来移除公开 `__NEXT_DATA__` / `og:audio` / CDN 地址，需要调整解析器。
- 抖音当前只支持单条视频/分享短链的浏览器采集；优先消费浏览器已签名的详情响应，回退到 DOM 直接媒体地址。如果详情响应不可用且页面只暴露 blob 或登录墙，会提示 Cookie/本地文件 fallback。项目不自行生成私有签名，也不维护复杂解密或专用 Sidecar。
- 微信视频号仍只识别来源，不自动获取媒体。
- 本地媒体必须是实际存在的文件；不存在的“路径字符串”不会进入本地媒体通道。
- 普通网页以 Trafilatura 为主，但复杂交互网站仍可能需要浏览器 fallback，且不承诺等同专业 crawler。
- PDF/DOCX/PPTX/XLSX 由 MarkItDown 提供实际转换能力，需要安装 `ingest2md[documents]`；ingest2md 本身不实现文档解析。
- SenseVoiceSmall 本地 backend 当前面向普通话、粤语、英语、日语、韩语；其他语言可显式选择更合适的云端 backend。
- 本地 ASR 首次使用需要下载模型；离线环境可预先准备模型并设置 `sensevoice_model_dir`。
- 音视频 ASR 仍可能有识别误差；需要精确字幕时显式输出 SRT/JSON 并复核。