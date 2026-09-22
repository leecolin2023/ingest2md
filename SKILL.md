---
name: ingest2md
description: Source-aware ingestion：把网页、视频、播客、本地音视频和可选 PDF/Office 文档转换为 portable Markdown；支持单条与可恢复批量任务。用于“先把内容可靠拿下来，再交给人或 LLM 阅读”的场景。
---

# ingest2md

## 目标

使用 `ingest2md` 时，把它视为 **ingestion layer**，不是总结器、RAG 系统或万能爬虫。

默认目标：

```text
Content Reference
→ 正确识别来源
→ 使用最合适的采集通道
→ 尽量保留原始语义
→ 输出 Markdown
```

## 何时使用

适合：

- 用户给出网页 / 视频 / 播客链接，希望保存成 Markdown；
- 用户给出 App 分享文案，需要自动取其中 URL；
- 用户给出本地音视频，希望转写成可读语料；
- 用户要批量处理很多来源，并需要 resume / retry；
- 用户给出 PDF / DOCX / PPTX / XLSX，并已安装可选 document 依赖。

不适合直接承担：

- 总结、改写、翻译；
- OCR / 图片理解；
- RAG / 向量库 / 知识图谱；
- 频道、主页、合集级爬虫；
- 私有平台协议逆向。

## 默认命令

```bash
ingest2md "<Content Reference>" -o output
```

先判断路由：

```bash
ingest2md "<Content Reference>" --explain
```

`--explain` 不抓取、不下载、不调用模型、不生成 Markdown。

## Content Reference 规则

单条输入规范化优先级：

1. 真实存在的本地文件；
2. Bilibili BV 号；
3. 分享文案中的第一条 `http(s)` URL；
4. 普通 URL / compatible web reference。

不要仅因为字符串以 `.mp4` / `.mp3` 结尾就当成本地媒体；文件必须真实存在。

## 平台语义

### 微信公众号

- 单篇公开文章；
- Camoufox 获取页面；
- 正文、代码块、图片本地化；
- 不做公众号历史文章批量抓取。

### 知乎

- 问题 URL 和回答 URL 都按“问题导向”处理；
- 尽可能获取当前可见回答，合并到一个 Markdown；
- `max_answers=0` 表示不主动设置数量上限，但不代表绝对抓全。

### 小红书

- 单篇笔记正文 + 当前可取得图片；
- 可使用 Netscape Cookie；
- 不默认 OCR / Vision。

### YouTube

```text
字幕 probe
├─ 有人工/自动字幕 → 直接转 TranscriptResult
└─ 无字幕 → 下载音频 → ASR
```

- 正常 ingestion 不要先跑播放 access probe；
- `--check-access` 是独立、更严格的音频访问诊断；
- Cookie、JS challenge、PO Token、网络出口属于外部访问层问题；
- 详细诊断见 `YOUTUBE_LOGIN.md`。

### Bilibili

- 支持单视频 / 分 P / BV 号；
- 字幕优先；
- 无字幕才 ASR；
- 不做 UP 主空间 / 合集采集。

### 小宇宙

- 只处理公开 episode；
- 提取节目简介 / Show Notes；
- 下载公开音频后先校验音轨和时长；
- Show Notes 有时间点时，用其组织语义章节；
- 没有章节时按 `transcript_window_seconds` 组织 Markdown。

### 抖音

- 只做单视频 / 分享短链的轻量采集；
- Playwright 打开真实页面；
- 优先读取浏览器已经产生的详情响应，回退 DOM 暴露的直接媒体地址；
- 候选媒体必须经过音轨 / 时长校验后才进入 ASR；
- 可选 `douyin_cookies_file`。

不得为提高成功率自行加入：

- `a_bogus` / `X-Bogus`；
- 私有详情 API；
- Sidecar；
- 主页 / 合集 / 评论 / 直播抓取。

如果只得到 `blob:`、登录墙或没有有效媒体候选，应明确失败，并建议用户下载后走本地媒体通道。

### 微信视频号

当前只识别，不自动获取媒体。
命中后应明确提示：先下载视频，再使用本地媒体路径。
不要让 Generic Web 假装抓取成功。

### 普通网页

- 先 HTTP 获取；
- Trafilatura 抽主要正文；
- 正文不足时再使用浏览器渲染；
- 目标是 readable main content，不是网页镜像。

### PDF / Office

- `.pdf/.docx/.pptx/.xlsx` 交给 Microsoft MarkItDown；
- 需要 `pip install -e ".[documents]"`；
- 不自行新增文档解析器。

## 本地音视频与 ASR

支持：

```text
.mp3 .m4a .wav .aac .flac .ogg .opus
.mp4 .mkv .mov .webm .avi .m4v
```

默认：

```text
asr_backend = sensevoice
```

三个 backend：

- `sensevoice`：本地 SenseVoiceSmall ONNX；
- `openai`：OpenAI-compatible `/audio/transcriptions`；
- `llm`：兼容 `chat/responses + input_audio` 的多模态模型。

规则：

- backend 自己负责预处理 / chunking；
- SenseVoice 默认 30 秒 WAV chunk、batch=2；
- Markdown 阅读窗口与 ASR chunk 解耦；
- 保留原语言，不自动翻译；
- 不另建 Provider Manager / Resolver Registry。

## 输出

默认只生成 Markdown。

只有用户明确需要时才开启：

```bash
--formats md,txt
--formats md,srt
--formats md,json
--keep-audio
--keep-chunks
```

Markdown 是 canonical output；SRT / JSON / TXT 是互操作产物。

## Batch

当用户需要处理多条来源时，使用统一 batch 调度，不要在平台 Adapter 外手写循环：

```bash
ingest2md batch sources.txt -o output/batch --resume
ingest2md batch sources.csv -o output/batch --take 20
ingest2md batch sources.jsonl -o output/batch --resume --retry-failed
```

manifest：

- TXT：自由粘贴文本，扫描全部 URL / BV；
- CSV：`source` 必填，`name,tags` 可选；
- JSONL：每行对象，`source` 必填，`name,tags` 可选。

当前边界：

- Batch **串行**执行；
- SQLite 保存任务状态；
- 支持 resume / retry / take；
- 同一批次复用 RuntimeContext；
- `name/tags` 当前只进入任务状态，不修改最终 Document；
- 抓取后的 `canonical_key` 当前只记录，不做二次 canonical 去重。

不要为了“提升速度”在外层同时启动多个 SenseVoice / Browser 任务；并发应在统一调度层基于 benchmark 和资源 semaphore 设计。

## Runtime 复用

同一个 RuntimeContext：

- 懒加载一个 ASR backend；
- SenseVoice backend 缓存模型；
- BrowserRuntime 复用 Chromium process；
- 每条网页任务使用独立 BrowserContext。

微信公众号使用 Camoufox 自己的 browser lifecycle，不属于共享 Chromium Runtime。

## 失败处理原则

优先给出真实状态，而不是假成功：

- unsupported / deferred → 明确来源与 fallback；
- auth / cookie → 提示登录态；
- rate limit / transient network → 保留可重试语义；
- invalid media → 在进入 ASR 前失败；
- transcription failure → 不伪装成空 Markdown。

## 新增能力的放置规则

1. 新平台语义 → `extractors/`；
2. 平台媒体获取细节 → `media/` 对应 helper；
3. 单条共用执行能力 → `engine.py` / `runtime.py`；
4. 批量任务状态 / 调度 → `batch/`；
5. ASR 输入差异 → 对应 transcription backend；
6. 最终阅读结构 → writers / Document output。

如果一个改动需要复制到多个 Adapter，先判断它是否其实属于共享层。

详细架构与边界见 `ARCHITECTURE.md`；安装、配置与用户命令见 `README.md`。
