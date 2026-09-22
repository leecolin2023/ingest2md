# ingest2md Architecture

本文描述 v0.9.3 当前主干的**实际架构与能力边界**。目标是让后续迭代先判断“应该扩展哪一层”，而不是继续在平台 Adapter 中堆重复基础设施。

## 1. 产品定位

`ingest2md` 是 source-aware ingestion layer：

```text
外部内容 / 本地内容
  ↓
识别来源
  ↓
获取可读内容
  ↓
规范化为 Document / TranscriptResult
  ↓
输出 portable Markdown
```

它位于“内容获取”和“LLM 分析”之间，不承担总结、RAG、Agent 推理、向量库等上层能力。

## 2. 核心设计原则

### 2.1 Source-aware，而不是万能 crawler

普通网页、视频平台、播客、公众号和本地文件的可靠获取方式并不相同。项目用有序 Router 把内容路由到 source-specific Adapter，而不是把所有 URL 都塞进一个浏览器抓取器。

### 2.2 Adapter 只拥有平台语义

平台 Adapter 可以决定：

- URL / Reference 是否属于自己；
- 该平台应该优先抓正文、字幕、Show Notes 还是媒体；
- 平台元数据如何映射到统一 Document；
- 平台特有的失败提示。

平台 Adapter 不应复制：

- Batch 调度；
- 通用 Cookie parser；
- 通用浏览器 runtime；
- 音频下载 / 校验 / 切片框架；
- ASR backend；
- Markdown / JSON / SRT writer。

### 2.3 Local-first media

媒体转写默认使用 SenseVoice ONNX，本地即可闭环。云端 ASR / LLM audio 是显式替代 backend，而不是默认依赖。

### 2.4 Markdown-first

Markdown 是 canonical user-facing output。JSON / TXT / SRT 是显式互操作格式，不反过来驱动主数据模型。

## 3. 单条执行链路

```text
CLI source
  ↓
load_settings()
  ↓
RuntimeContext
  ↓
IngestionEngine.ingest_one()
  ↓
normalize_reference()
  ↓
find_extractor()
  ↓
Extractor.extract()
  ↓
Document
  ↓
write_document()
```

核心模块：

| 模块 | 职责 |
|---|---|
| `cli.py` | 参数解析、single / batch 入口、诊断命令 |
| `config.py` | Settings、配置迁移、环境变量与参数校验 |
| `engine.py` | 单条 ingestion 的唯一应用核心 |
| `router.py` | Reference 规范化后按顺序选择 Adapter |
| `extractors/` | 平台 / 内容类型语义 |
| `runtime.py` | 长生命周期昂贵资源 |
| `transcription/` | TranscriptResult、ASR backend、字幕转换与 writers |
| `media/` | 音频预处理、下载、平台媒体获取辅助 |
| `model.py` | Document 与最终输出 writer |
| `batch/` | manifest、SQLite 状态、串行调度 |

## 4. Router 与 Adapter 顺序

当前 built-in 顺序：

```text
DeferredMediaExtractor
DouyinExtractor
LocalMediaExtractor
DocumentExtractor
WeChatExtractor
BilibiliExtractor
YouTubeExtractor
XiaoyuzhouExtractor
ZhihuExtractor
XiaohongshuExtractor
GenericWebExtractor
```

顺序本身是架构约束，因为 `GenericWebExtractor` 可以匹配绝大多数 HTTP(S) URL。
任何有平台语义的来源都必须排在 Generic Web 前面，否则会产生“路由成功但语义错误”的假成功。

`DeferredMediaExtractor` 同样必须靠前：对于微信视频号这类“已识别、但当前不稳定支持”的平台，应明确失败并提示 fallback，而不是掉入 Generic Web。

## 5. Content Reference 规范化

Reference 不是 URL 的同义词。

单条模式目前可识别：

```text
existing local path
BV id
share text containing URL
normal URL / compatible web reference
```

批量 TXT 进一步使用 `extract_references()` 扫描自由文本中的全部 URL / BV。
CSV / JSONL 则保持结构化语义。

本地文件判断必须基于“路径真实存在”，不能因为字符串后缀看起来像 `.mp4` 就当成本地媒体。

## 6. Extractor 分层

### 6.1 Text / page sources

- 微信公众号：Camoufox 获取文章 HTML，抽正文、代码块与图片；
- 知乎：浏览器展开 / 滚动，按问题维度聚合当前可取得回答；
- 小红书：浏览器渲染，抽正文与可取得图片；
- Generic Web：先 HTTP + Trafilatura，正文不足再浏览器渲染。

### 6.2 Subtitle-first video sources

YouTube / Bilibili 采用：

```text
metadata / subtitle probe
  ├─ subtitle exists → subtitles_to_transcript()
  └─ no subtitle → audio download → transcribe_audio()
```

“有字幕时不下载音频”是默认优化；只有显式 `--keep-audio` 才可能额外下载。

### 6.3 Audio-first sources

小宇宙、抖音、本地媒体最终都复用同一 transcription abstraction。

小宇宙额外做：

- 公共页面元数据解析；
- Show Notes 提取；
- 音频下载后的音轨 / 时长校验；
- Show Notes 时间点 → 语义章节。

抖音额外做：

- Playwright 打开真实页面；
- 收集浏览器已产生的详情响应 / DOM 媒体候选；
- 逐候选下载；
- 音轨 / 时长校验；
- 不实现私有签名。

### 6.4 Delegated document source

PDF / DOCX / PPTX / XLSX 只负责识别和委托 Microsoft MarkItDown。
这是一条明确的“复用成熟基础设施”边界，而不是待补齐的自研解析器。

## 7. Transcription architecture

统一入口：

```text
transcribe_audio(audio_path, work_dir, settings, backend=...)
```

当前三个 backend：

```text
SenseVoiceBackend
OpenAIASRBackend
LLMAudioBackend
```

关键规则：**backend 自己拥有预处理与 chunking**。

- SenseVoice：短 WAV chunk + true batch inference；
- OpenAI-compatible ASR：较长 MP3 chunk；
- multimodal LLM：自己的 audio chunk / API 语义。

因此不需要再建立 MediaProviderManager、ASR Provider Registry 或一套统一切片器强迫所有模型走相同输入。

`TranscriptResult` 保留底层 segment；最终 Markdown 的阅读窗口由 writer 聚合。
这意味着：

```text
ASR chunk size != Markdown reading window
```

v0.9.3 后，小宇宙还能用 Show Notes 时间点替换固定窗口，形成语义章节。

## 8. RuntimeContext

`RuntimeContext` 用于“同一执行生命周期内值得复用的昂贵资源”，而不是任务状态。

当前包括：

- lazy ASR backend；
- `SenseVoiceBackend` 内缓存已加载模型；
- `BrowserRuntime` 复用 Chromium process。

对需要 browser runtime 的 Adapter，每条任务仍创建独立 `BrowserContext` 并在结束时关闭，避免 Cookie / 页面状态串任务。

需要注意：微信公众号当前使用 Camoufox 自己的 browser lifecycle，**不在共享 Chromium Runtime 中**；YouTube / Bilibili 主要走 yt-dlp，也不依赖该浏览器 runtime。

这说明 RuntimeContext 的目标不是“所有来源都必须复用同一种浏览器”，而是只复用真正共享且稳定的资源。

## 9. Batch architecture

```text
manifest
  ↓
loader
  ↓
BatchItem[]
  ↓
TaskStore (SQLite)
  ↓
BatchRunner
  ↓
IngestionEngine
```

### 9.1 当前语义

- 串行执行；
- 一个任务失败不阻断其他任务；
- 支持 `resume`；
- 支持 `retry_failed`；
- 支持 `take N`；
- 成功输出丢失时，resume 会把任务重新置为 pending；
- config fingerprint 变化会形成新的任务版本。

### 9.2 去重边界

任务注册阶段使用规范化 source / task key 避免相同输入重复建任务。
抓取完成后会记录：

```text
canonical_key = source_type + ":" + source_id
```

但 **canonical_key 当前只记录，不参与二次合并或去重**。
也就是说两个不同分享 URL 如果最终解析到同一个平台对象，目前仍可能各自完成一次 ingestion。

### 9.3 name / tags 边界

CSV / JSONL 可以携带 `name,tags`，TaskStore 也会保存。
但 v0.9.3 的 `IngestionEngine` 尚未把它们写入 `Document` 或输出命名。
因此它们当前是调度元数据 / 预留字段，不应在文档中描述成“自定义标题和标签输出”。

### 9.4 为什么暂不并发

不同来源的主要瓶颈并不相同：

- SenseVoice 吃 CPU / 内存；
- 浏览器任务吃 Chromium 资源；
- 网络平台可能限流；
- yt-dlp / ffmpeg 又是独立进程。

在缺少真实 benchmark 与统一资源 semaphore 前，直接加入并发容易把吞吐问题变成稳定性问题。
因此当前设计先把“可恢复、资源复用、任务隔离”做对，再决定并发。

## 10. Document 与输出

统一模型：

```text
Document
├─ title
├─ source_url
├─ source_type / source_id
├─ metadata
├─ body_md
├─ transcript?
├─ image_map
├─ attachments
├─ original_title
└─ original_description
```

`write_document()` 始终保证 Markdown。
只有出现图片 / 附件 / 额外格式时才创建内容目录；纯文本 Markdown 保持扁平输出。

这种策略避免每条内容都生成一堆 debug artifact，同时又保留 SRT / JSON / TXT 作为显式互操作能力。

## 11. 错误边界

Batch 会做轻量错误分类，例如：

```text
unsupported
input_missing
timeout
rate_limited
transient_network
auth_required
invalid_media
transcription_failed
failed
```

这里的目标是让用户知道“下一步该做什么”，不是建立复杂异常 taxonomy。

对于平台限制，优先：

1. 返回清楚错误；
2. 提示 Cookie / 网络 / 本地文件 fallback；
3. 保持 Adapter 边界；
4. 不为了“成功率”引入不可维护的私有逆向。

## 12. 现阶段架构债务 / 后续自然演进点

下面这些是当前代码已经暴露出来、且与产品定位一致的自然演进点：

### 12.1 Batch metadata 真正进入输出

如果未来确有需求，应明确设计 `name/tags` 如何映射到 Document，而不是让字段长期停留在数据库。

### 12.2 canonical identity 二次去重

若批量规模扩大，可以在成功解析 `source_type/source_id` 后做 canonical duplicate detection。
但需要先定义“重复时保留哪一个输出 / 状态如何归并”。

### 12.3 资源感知并发

只有在 benchmark 证明串行成为主要瓶颈后，再考虑：

- 按任务类型分类；
- 浏览器 / ASR / 下载分别设置 semaphore；
- 保持单条 IngestionEngine 不变。

不建议在 Adapter 内自己开并发。

### 12.4 Adapter capability contract

当前 Protocol 很轻，只要求 `name/description/match/extract`。
只有当上层确实需要机器可读的 capability metadata 时，再扩展 contract；不要为了“架构完整”提前造 Registry schema。

## 13. 新功能应该加在哪一层

判断顺序：

```text
这是新的平台语义吗？
  ├─ 是 → Extractor / source-specific media helper
  └─ 否
      ↓
是所有来源都需要的执行能力吗？
  ├─ 是 → Engine / Runtime / shared utility
  └─ 否
      ↓
是批量任务状态 / 调度问题吗？
  ├─ 是 → batch/
  └─ 否
      ↓
是转写 backend 自己的输入问题吗？
  ├─ 是 → transcription backend
  └─ 否
      ↓
是最终呈现问题吗？
  └─ writers / Document output
```

如果一个需求必须同时改很多平台 Adapter，通常意味着它其实不应该属于 Adapter。

## 14. 当前架构结论

v0.9.x 的关键变化不是“多支持了几个网站”，而是项目已经形成了四条稳定主轴：

1. **Source-aware Router / Adapter**：平台差异被隔离；
2. **Shared Engine / Runtime**：single 与 batch 共用执行核心，昂贵资源可复用；
3. **Transcription abstraction**：字幕、ASR backend、Markdown presentation 解耦；
4. **Durable Batch**：任务状态、恢复与错误隔离独立于平台。

因此下一阶段不应该回到“继续堆平台脚本”的方向，而应优先补足上述抽象已经暴露出的真实缺口，同时继续保持产品边界。
