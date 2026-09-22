# ingest2md

> Source-aware content ingestion for AI / agents: turn web pages, media, documents and pasted references into portable Markdown.

`ingest2md` 的目标不是做一个“万能爬虫”，也不是直接做总结、RAG 或知识库。
它负责的是更靠前、也更基础的一层：**识别内容来源 → 选择合适的采集方式 → 尽量保留原始语义 → 输出可移植 Markdown**。

当前版本：**v0.9.3**。主干 CI 覆盖 Python 3.10 / 3.12，当前测试集为 **55 tests**。

## 1. 它解决什么问题

不同内容源的“拿内容”方式差异很大：普通网页适合正文抽取，YouTube / Bilibili 应优先拿字幕，小宇宙需要 Show Notes + 音频转写，微信公众号需要处理图片与特殊 HTML，本地音视频则应直接进入 ASR。

`ingest2md` 把这些差异收敛到统一入口：

```text
Content Reference
  ↓
normalize
  ↓
Router
  ↓
source-specific Extractor
  ↓
Document
  ↓
Markdown-first output
```

单条任务和批量任务共用同一个 `IngestionEngine`；批量模式只是增加任务状态、恢复和资源复用，不复制平台逻辑。

## 2. 当前能力边界

下面的“已接入”表示代码中存在明确 Adapter 和完整处理路径；现有自动化测试主要覆盖核心路由、媒体、Batch 与回归行为，并不等于每个平台都有实时联网测试。在线内容是否能成功获取仍会受到登录、反爬、网络出口和页面结构变化影响。

| 来源 / 输入 | 当前级别 | 默认处理路径 | 明确边界 |
|---|---|---|---|
| 微信公众号 | 已接入 | 单篇公开文章 → Camoufox → 正文 / 图片本地化 → Markdown | 不做公众号历史文章批量抓取 |
| 知乎 | 已接入 | 问题或回答 URL → 归一到问题 → 尽可能收集可见回答 → 单个 Markdown | “尽可能多”不等于绝对抓全；登录态和动态加载会影响结果 |
| 小红书 | 轻量接入 | 单篇笔记 → 浏览器渲染 → 正文 + 当前可取得图片 | 不做 OCR / Vision，不承诺登录墙后的内容 |
| YouTube | 已接入 | 单视频 → 人工/自动字幕优先 → 无字幕才下载音频 → ASR | 不做频道 / 播放列表采集；访问可能受 Cookie、JS challenge、PO Token、网络出口影响 |
| Bilibili | 已接入 | 单视频 / 分 P / BV 号 → 字幕优先 → ASR fallback | 不做 UP 主空间、合集批量采集 |
| 小宇宙 | 已接入 | 公开单集 → Show Notes → 公开音频 → 校验 → ASR → 章节化 Markdown | 只处理公开 episode；不接私有 API |
| 抖音 | 轻量接入 | 单视频 / 分享短链 → Playwright → 浏览器已产生的详情响应或 DOM 媒体候选 → 音轨/时长校验 → ASR | 不实现 `a_bogus` / `X-Bogus`、私有签名、主页/合集/评论/直播；登录墙或只暴露 `blob:` 时会失败 |
| 微信视频号 | 仅识别 | 命中来源后明确提示改走本地文件 | 当前不自动获取媒体 |
| 普通网页 | 已接入 | HTTP → Trafilatura 主正文 → 不足时浏览器 fallback | 目标是“主要正文”，不是完整网页镜像或站点爬虫 |
| 本地音视频 | 已接入 | 本地文件 → 配置 ASR backend → 原语言转写 → Markdown | 不做说话人分离、强制对齐、自动翻译 |
| PDF / DOCX / PPTX / XLSX | 可选能力 | 委托 Microsoft MarkItDown → Markdown | 需安装 `.[documents]`；项目不自行维护文档解析器 |

本地音视频扩展名：

```text
audio: .mp3 .m4a .wav .aac .flac .ogg .opus
video: .mp4 .mkv .mov .webm .avi .m4v
```

## 3. 明确不做什么

当前产品边界刻意保持清晰：

- 不在 ingestion 阶段自动总结、改写或翻译内容；
- 不把 OCR / Vision 当成默认网页或图片处理链路；
- 不建设通用站点爬虫、频道/主页/合集抓取器；
- 不自行维护 YouTube、抖音等平台的私有签名或逆向协议；
- 不重复造 PDF / Office 解析引擎；
- 不引入 VAD、speaker diarization、WhisperX、pyannote 等重型语音栈；
- 不把 Batch 做成并发 worker / DAG 框架；当前批量仍是**串行、可恢复**执行；
- 不直接承担 RAG、向量库、知识图谱或 Agent 推理层。

这也是项目的核心设计原则：**平台语义自己维护，通用基础能力尽量复用成熟组件。**

## 4. 输入：Content Reference

CLI 输入不只接受 URL。当前统一支持：

```text
Content Reference
= URL
| App 分享文案中的 URL
| Bilibili BV 号
| 已存在的本地音视频文件
| 本地 / URL PDF、DOCX、PPTX、XLSX
```

单条模式会从分享文案中取第一条可识别 URL；批量 TXT 则会扫描一段自由文本中的**全部 URL / BV 号**。

```bash
ingest2md "6.48 复制打开抖音…… https://v.douyin.com/xxx/"
ingest2md "BV1xxxxxxxxx"
ingest2md "./meeting.m4a"
ingest2md "./report.pdf"
```

可先只看路由，不进行网络访问或模型调用：

```bash
ingest2md "<Content Reference>" --explain
```

## 5. 安装

要求 Python 3.10+。

```bash
git clone https://github.com/leecolin2023/ingest2md.git
cd ingest2md
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install -e .
python -m playwright install chromium
```

微信公众号首次使用 Camoufox 还需要：

```bash
python -m camoufox fetch
```

### 本地 ASR

默认 ASR backend 是 SenseVoice ONNX。需要本地转写时安装：

```bash
python -m pip install -e ".[local-asr]"
```

并确保系统可调用 `ffmpeg` / `ffprobe`。
首次实际使用 SenseVoice 时会自动下载 / 定位 `iic/SenseVoiceSmall`；也可以用 `sensevoice_model_dir` 指向已准备好的模型目录。

### 文档转换

```bash
python -m pip install -e ".[documents]"
```

## 6. 快速使用

### 单条 ingestion

```bash
ingest2md "https://example.com/article"
ingest2md "https://www.youtube.com/watch?v=VIDEO_ID"
ingest2md "https://www.xiaoyuzhoufm.com/episode/<episode-id>"
ingest2md "./meeting.mp4" -o output
```

默认输出只有 Markdown。额外格式需要显式开启：

```bash
ingest2md "./meeting.mp4" --formats md,txt,srt,json
ingest2md "./meeting.mp4" --keep-audio
```

### 批量 ingestion

```bash
ingest2md batch sources.txt -o output/batch --resume
ingest2md batch sources.csv -o output/batch --take 20
ingest2md batch sources.jsonl -o output/batch --resume --retry-failed
```

支持三种 manifest：

- `TXT`：自由粘贴文本，扫描全部 URL / BV；独占一行的本地文件和裸域名继续兼容；
- `CSV`：至少包含 `source`，可选 `name,tags`；
- `JSONL`：每行一个对象，必须有 `source`，可选 `name,tags`。

批量状态保存在输出目录的 `.ingest2md-batch.sqlite3`。

> 当前 `name/tags` 会进入 Batch 任务状态，但**还不会修改最终 Document 标题、正文或文件名**。它们目前属于任务元数据，而不是输出语义。

批量执行当前有意保持串行：

- 一个任务失败不会中断后续任务；
- `--resume` 可恢复中断任务并检查已成功输出是否仍存在；
- `--retry-failed` 可重新进入失败任务；
- `--take N` 可限制本次处理数量；
- 同一批次复用一个 `RuntimeContext`，避免重复初始化昂贵资源。

## 7. 字幕与 ASR

媒体类来源的默认原则是：**字幕优先，本地 ASR fallback，云端显式 opt-in。**

```text
YouTube / Bilibili
  ├─ 有平台字幕 → TranscriptResult → Markdown
  └─ 无字幕 → 下载音频 → ASR backend → TranscriptResult → Markdown

Local media / Xiaoyuzhou / Douyin
  └─ 媒体 → 校验/预处理 → ASR backend → TranscriptResult → Markdown
```

当前 ASR backend：

| backend | 用途 | 默认 |
|---|---|---|
| `sensevoice` | SenseVoiceSmall ONNX，本地 CPU 转写 | ✅ |
| `openai` | OpenAI-compatible `/audio/transcriptions` | 可选 |
| `llm` | 兼容 `chat/responses + input_audio` 的多模态模型 | 可选 |

每个 backend 自己负责预处理和切片；Markdown 展示窗口由 `transcript_window_seconds` 单独控制，避免把“模型推理 chunk”与“最终阅读结构”绑死。

## 8. 输出模型

内部统一结果是 `Document`，Markdown 是 canonical output。

```text
Document
├─ title / source_url / source_type / source_id
├─ metadata
├─ body_md
├─ transcript (optional)
├─ image_map / attachments
└─ original_title / original_description
```

默认纯文本 Markdown 直接写到输出目录；当存在本地图片、附件或额外格式时，会为该内容创建独立目录。

支持显式输出：

- `md`：始终存在；
- `txt`：转写纯文本或正文；
- `srt`：仅有 transcript 时有意义；
- `json`：Document 的结构化互操作结果。

## 9. 配置

复制示例：

```bash
cp config.example.yaml config.yaml
```

常用配置：

```yaml
asr_backend: "sensevoice"
asr_language: "auto"
transcript_window_seconds: 300

sensevoice_chunk_seconds: 30
sensevoice_batch_size: 2

output_dir: "output"
formats: ["md"]

youtube_cookies_file: ""
bilibili_cookies_file: ""
zhihu_cookies_file: ""
xiaohongshu_cookies_file: ""
douyin_cookies_file: ""
```

站点专用 Cookie 优先于通用 `cookies_file`。Cookie 使用 Netscape 格式，并应视为登录凭据，不要提交到 Git。

YouTube 的 Cookie、JS challenge 与音频播放访问诊断见 [YOUTUBE_LOGIN.md](YOUTUBE_LOGIN.md)。

## 10. 当前架构

```text
CLI
├─ single
└─ batch
    ↓
IngestionEngine
    ↓
normalize_reference
    ↓
ordered Router
    ↓
Extractor
    ├─ web / browser acquisition
    ├─ subtitle-first media acquisition
    ├─ document delegation
    └─ local media
    ↓
TranscriptResult (optional)
    ↓
Document
    ↓
write_document()
```

批量模式额外包含：

```text
Batch loader
  ↓
SQLite TaskStore
  ↓
serial BatchRunner
  ↓
shared RuntimeContext
  ├─ lazy shared ASR backend / cached SenseVoice model
  └─ shared Chromium process / isolated BrowserContext per task
```

更详细的模块职责、路由顺序、运行时复用、状态语义和扩展规则见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 11. 诊断与失败处理

路由诊断：

```bash
ingest2md "<reference>" --explain
```

YouTube 音频访问诊断：

```bash
ingest2md "https://www.youtube.com/watch?v=VIDEO_ID" --check-access
```

设计上，平台无法稳定获取时应**明确失败并给出 fallback**，而不是让 Generic Web 伪装成成功。例如微信视频号会直接提示先下载媒体，再走本地音视频通道。

## 12. 开发与测试

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

CI 在 push 到 `main` 和 pull request 时运行 Python 3.10 / 3.12。
当前 v0.9.3 主干 CI 已通过 55 tests，详见 [TEST_REPORT.md](TEST_REPORT.md)。

新增来源时优先遵循以下规则：

1. 只有存在明确“平台语义”时才新增 Adapter；
2. 更具体的 Adapter 必须排在 Generic Web 之前；
3. Adapter 只负责一条内容的采集，不承担 Batch 调度；
4. 音频转写复用统一 `transcribe_audio()` / ASR backend；
5. 不为单个平台复制浏览器、Cookie、下载、ASR、输出等基础设施；
6. 识别到但无法稳定获取的平台，应明确 unsupported / deferred，不做假成功。

## 13. 最近版本

- **v0.9.3**：长音频展示结构与 ASR chunk 解耦；小宇宙加入音频完整性校验和 Show Notes 章节化转写；
- **v0.9.2**：Batch TXT 升级为自由文本 Reference scanner；
- **v0.9.1**：引入 long-lived `RuntimeContext`，批量复用 ASR backend、SenseVoice 模型和 Chromium；
- **v0.9.0**：引入统一 `IngestionEngine`、SQLite Batch 状态与 resume / retry / take。

更早的演进历史可直接查看 Git commit history；README 不再维护逐版本的完整实现日志。
