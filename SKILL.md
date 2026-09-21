---
name: ingest2md
description: 把网页链接、App 分享文案和本地音视频转换为本地、可直接阅读并可批量交给 LLM 的 Markdown 语料。支持微信公众号、知乎、小红书、Bilibili、YouTube、小宇宙、抖音单视频、普通网页、本地音视频和可选 PDF/Office 文档；微信视频号可识别但暂不自动获取媒体。
---

# ingest2md — Content Reference → LLM Markdown Corpus

## 何时使用

当用户希望“读取 / 保存 / 归档 / 整理 / 分析”一个在线内容或音视频，并希望后续让人或大模型继续阅读时使用。

支持的输入不再局限于 URL：

- 微信公众号文章；
- 知乎问题或回答 URL：默认按**问题导向**，获取问题和尽可能多回答；
- 小红书笔记；
- Bilibili 单视频/分P或 BV 号；
- YouTube 单视频；
- 小宇宙单集；
- 抖音单视频 / 分享短链；
- 普通 http/https 网页；
- App 分享文案：自动取其中第一条 http(s) URL；
- 本地 MP3/M4A/WAV/AAC/FLAC/OGG/OPUS；
- 本地 MP4/MKV/MOV/WebM/AVI/M4V；
- 播客、访谈、会议录音等希望转成大模型语料的本地媒体。

## 默认调用

```bash
ingest2md "<Content Reference>" -o <输出目录>
```

例如：

```bash
ingest2md "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e" -o archive
ingest2md "6.48 复制打开抖音…… https://v.douyin.com/akR8LCIaTMI/ ……" -o archive
ingest2md "./meeting.m4a" -o archive
ingest2md "D:\Downloads\video.mp4" --limit-seconds 60 -o archive
```

默认只有 Markdown。不要为了“结构化”主动生成 JSON、raw HTML、manifest、下载媒体等额外产物。

## 平台语义

- 微信：文章正文 + 本地图片。
- 知乎：问题 + 尽可能多回答，合并成一个 Markdown；不是只保存当前回答。
- 小红书：正文 + 当前可取得的笔记图片；默认不跑 OCR/Vision。
- B站/YouTube：优先使用平台人工/自动字幕；有字幕直接保留原语言，没有字幕才进入 ASR。
- 小宇宙：节目简介 / Show Notes + 公开音频转写；下载后先校验音轨/时长，Show Notes 时间点优先作为语义章节；默认使用本地 SenseVoice，保留原语言。
- 抖音：用现有 Playwright 打开单视频/分享短链，优先消费浏览器会话已经取得的详情响应，回退到 DOM 暴露的直接 http(s) 媒体地址，再复用现有 ASR；不实现私有签名。
- 本地音视频：默认 `SenseVoiceBackend` 本地转写；也可显式选择 OpenAI-compatible ASR 或多模态 LLM audio。Backend 自己决定切片格式与时长。
- 普通网页：HTTP 获取后优先用 Trafilatura 提取正文，必要时才用浏览器 fallback。
- PDF/DOCX/PPTX/XLSX：交给可选的 Microsoft MarkItDown Adapter，不自行实现文档解析。

## v0.11 核心架构规则

v0.11 的应用主链路固定为：

```text
Content Reference
→ Router / Adapter
→ Resolve Identity
→ Extract Document
→ Transcript Presentation（如有）
→ Writer
→ Markdown
```

批量模式允许在 `Resolve Identity` 后和 `Extract Document` 后各做一次 canonical dedupe；单条模式仍通过同一个 `IngestionEngine.ingest_one()` 组合这些步骤。

边界要求：

- Adapter 只负责平台语义与采集，不引入 ProviderManager / PipelineEngine / Scheduler；
- 已知平台尽量提供稳定 semantic identity，例如 `youtube:VIDEO_ID`、`bilibili:BV_pN`；
- 没有 `source_id` 的内容，输出文件名必须使用稳定 source URL 短哈希防覆盖；
- CSV/JSONL 的 `name/tags` 属于最终产物元数据；变化时成功任务需要重新生成；
- timeout / 429 / 502 / 503 / 504 等临时错误允许自动重试，默认最多 3 次；`--retry-failed` 仍保留人工兜底；
- 下载成功但后续失败的网络媒体可保留在 Runtime media cache，成功后默认清理；
- `transcript_enhance=llm` 只允许修改 Markdown presentation 文本，不得修改 raw `TranscriptResult`；SRT/JSON 始终基于原始 segments；
- 当前 Batch 保持串行；没有真实 benchmark 前不引入并发队列或 ASR semaphore。

## v0.8.3 本地 ASR 性能规则

- SenseVoice 默认 `sensevoice_chunk_seconds=30`、`sensevoice_batch_size=2`；
- SenseVoice 必须真正批量传入多个 WAV 文件，不能只把 `batch_size` 传给模型后仍逐片调用；
- 音频切片使用一次 ffmpeg segment 完成，避免按 chunk 重复启动进程；
- 可通过 `--sensevoice-batch-size 4` 做本机 benchmark，但不要假设 batch 越大一定越快；
- 性能日志应保留 preprocess / model setup / inference / total / RTF，便于后续基于实测优化。

## v0.8 音视频规则

- 默认 `asr_backend=sensevoice`，不要求任何付费 API。
- SenseVoice 依赖按需安装：`pip install -e ".[local-asr]"`。
- 字幕与 ASR 结果保持原语言，不做自动中文翻译。
- `openai` backend 仅负责 OpenAI-compatible `/audio/transcriptions`。
- `llm` backend 负责兼容 `chat/responses + input_audio` 的多模态模型；Opencode 只是默认示例配置。
- 不建立 Provider Manager / Registry；`transcribe_audio()` 只选 backend，各 backend 自己做预处理与切片。

## Content Reference 规则

输入规范化顺序：

1. 如果整段输入本身是**真实存在的本地文件**，按 Local Media 处理；
2. 否则如果是 BV 号，规范化成 Bilibili URL；
3. 否则从分享文案中提取第一条 `http(s)` URL；
4. 否则按普通 URL 兼容规则处理。

不要因为字符串以 `.mp4` / `.mp3` 结尾，就假定它是本地文件；文件必须真实存在。

## 抖音规则

抖音单视频已进入轻量支持范围：

```text
分享文案 / v.douyin.com / douyin.com/video/...
↓
Playwright 渲染真实页面
↓
video.currentSrc / video.src / source[src]
↓
直接 http(s) 媒体
↓
现有 transcribe_audio()
```

约束：

- 匿名访问优先，必要时允许 `--douyin-cookies-file`；
- 页面只暴露 `blob:`、登录墙或无直接媒体地址时必须明确失败；
- 失败后提示更新 Cookie 或下载后走本地媒体通道；
- 不自行实现 `a_bogus` / `X-Bogus`、私有 API、Sidecar、主页/合集/评论/直播。

## 已识别但未稳定支持的平台

微信视频号仍不得让 Generic Web 假装抓取成功。识别到：

```text
weixin.qq.com/sph/
channels.weixin.qq.com
```

应明确提示下载视频后走本地媒体通道。

## 小宇宙规则

只处理公开单集：

```text
https://www.xiaoyuzhoufm.com/episode/<24位episode id>
```

解析优先级：

1. `__NEXT_DATA__` 中的 episode；
2. `og:title / og:description / og:audio`；
3. `media.xyzcdn.net` 音频 URL 正则兜底。

取得公开音频后先做 ffprobe 音轨/时长校验，再交给现有 `transcribe_audio()`。不要建立第二套播客转写框架。

最终正文应保持：

```markdown
## 节目简介
...

## Show Notes
...

## 转写正文

### 00:00–05:00
...
```

默认不要生成 `episode.json`、`raw.html`、`audio.m4a` 等调试/中间产物。

## 需要登录态时

Cookie 使用 Netscape 格式：

```bash
ingest2md "<知乎URL>" --zhihu-cookies-file zhihu-cookies.txt
ingest2md "<小红书URL>" --xiaohongshu-cookies-file xhs-cookies.txt
ingest2md "<YouTubeURL>" --youtube-cookies-file youtube-cookies.txt
ingest2md "<抖音URL>" --douyin-cookies-file douyin-cookies.txt
```

## 路由解释

```bash
ingest2md "<Content Reference>" --explain
```

只解释输入类型、识别来源、Adapter 与处理计划；不抓取、不下载、不调用模型，也不生成文件。

## 额外产物只有用户需要时才开

```bash
--formats md,srt
--formats md,json
--formats md,txt
--keep-audio
--keep-chunks
```

本地媒体使用 `--keep-audio` 时保存的是输入媒体副本 `source_media.<ext>`。

## 规则

- 输入尽量用引号完整包裹，特别是分享文案和 Windows 路径。
- 知乎默认“尽可能多”，但不承诺绝对抓全；如果用户只想快速验证，可加 `--max-answers 10`。
- 小宇宙与本地媒体都复用 `transcribe_audio()`；ASR backend 自己负责切片，不新增 MediaProviderManager / Resolver Registry。
- 不把采集阶段变成总结阶段：默认尽量保留正文，后续分析交给 LLM。
- 对不稳定网站，优先返回可读的部分结果/清晰错误，不建设重型审计产物。
- 微信视频号等 deferred 平台必须明确失败，不得悄悄降级成 Generic Web；抖音只在浏览器取得直接媒体 URL 时继续。
- 详细安装、配置、边界见 `README.md`。


## 批量处理

当用户要长期处理多条来源时，不要在平台 Adapter 外手写循环，使用统一 batch 调度：

```bash
ingest2md batch sources.txt -o output/batch --resume
ingest2md batch sources.csv -o output/batch --take 20
ingest2md batch sources.jsonl -o output/batch --resume --retry-failed
```

支持：

- TXT：自由粘贴文本。自动提取全部 http/https URL 与 BV 号；多个链接可位于同一行；独占一行的本地文件路径/裸域名继续兼容；无引用的普通说明文字忽略；
- CSV：至少包含 `source` 列，可选 `name,tags`；
- JSONL：每行一个对象，必须有 `source`，可选 `name,tags`。

批量任务状态保存在输出目录的 `.ingest2md-batch.sqlite3`。SQLite 只属于 batch 调度，不进入平台 Adapter。

v0.9.1 的 batch 会复用一个 RuntimeContext：

- 同一批次复用 ASR backend；
- SenseVoice ONNX 模型只加载一次；
- 需要浏览器的平台复用一个 Chromium 进程；
- 每条任务仍使用独立 BrowserContext，避免 Cookie/页面状态串任务。

v0.11 的 batch 仍是串行执行，但已经具备 canonical duplicate、自动 retry、失败媒体缓存与 `ingest2md batch status`。不要为了并发自行在外层同时启动多个 SenseVoice 任务；并发与资源 semaphore 留给后续真实 benchmark。


### TXT 自由文本扫描

TXT 不是严格表格，而是低门槛的“随手粘贴区”。处理规则：

1. 从每段文本中按出现顺序提取全部 `http/https` URL 和 Bilibili BV 号；
2. 一行中出现多个链接时拆成多个 BatchItem；
3. 精确重复引用只保留第一次；
4. 没有 URL/BV 时，若整行是实际存在的本地文件，则保留为本地任务；
5. 独占一行的裸域名（如 `example.com/article`）继续兼容；
6. 其他普通说明文字忽略，不尝试补成伪 URL。

不要把这个 Scanner 写成抖音正则；它属于 Content Reference 通用输入能力。CSV/JSONL 继续保持结构化字段语义。
