# ingest2md v0.10.0 Test Report

功能代码验证基线：`feat/transcript-normalization@5ebfbea03e90e5f4fe62b813c6dbddba67791449`

GitHub Actions run：`35709378656`

结果：**success**

CI matrix：

```text
Python 3.10
Python 3.12
```

每个 matrix 执行：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

当前测试文件包含 **62 个 test functions**，Python 3.10 / 3.12 的 pytest 均通过。

## 覆盖重点

### Reference / Router

- App 分享文本 URL 提取；
- BV 号规范化；
- 本地文件只在真实存在时路由；
- 特定平台优先于 Generic Web；
- 微信视频号 deferred 路由；
- `--explain` dry-run。

### Source adapters

- Generic Web 正文抽取与 Trafilatura 优先策略；
- YouTube 字幕优先与 ASR fallback；
- Bilibili 字幕优先；
- 小宇宙公开 episode 解析、Show Notes 章节、音频完整性校验；
- 小宇宙从标题、Show Notes、嘉宾与产品 / 英文术语构造 `NormalizationHints`；
- 抖音详情响应 / DOM / 浏览器网络媒体候选顺序与无效媒体剔除；
- MarkItDown document delegation。

### Transcription

- 默认 SenseVoice local-first；
- 三种 ASR backend factory；
- backend 自己拥有预处理与 chunking；
- Markdown 阅读窗口与底层 ASR segment 解耦；
- Transcript Normalization 默认 `basic`；
- `f d e → FDE` 等确定性缩写清理；
- SenseVoice 富文本装饰符清理；
- `Segment.raw_text` 保留原始 ASR；
- Normalization 不改变 segment 数量、顺序与时间戳；
- LLM normalization 失败自动回退 basic；
- 可选 LLM normalization 保留 source hints 与 segment invariants；
- SRT / JSON 继续复用统一 TranscriptResult。

### Batch / Runtime

- TXT / CSV / JSONL manifest；
- TXT 自由文本多 Reference scanner；
- IngestionEngine 作为 single / batch 共用核心；
- SQLite resume / retry；
- 单任务失败隔离；
- RuntimeContext 懒加载并复用 ASR backend；
- SenseVoice 模型跨任务复用；
- Chromium process 复用且 BrowserContext 按任务隔离。

## 测试不代表什么

这些测试主要验证内部行为与回归，不等于对第三方网站的实时可用性承诺。

在线平台仍可能因为登录 / Cookie、反爬、人机校验、网络出口、页面结构变化、地区限制或平台策略而失败。

## v0.10.0 回归重点

- Normalization 位于统一 ASR 出口，而不是复制到各 Adapter；
- 平台原生字幕不经过 Normalization；
- `basic` 为本地默认能力，不需要付费 API；
- `llm` 只是显式可选增强，单窗口失败不能让成功 ASR 任务失败；
- Raw ASR 与 normalized text 可同时保留，便于后续评测和问题定位；
- 小宇宙只负责产生通用 hints，Normalizer 不依赖平台实现；
- 没有引入 speaker diarization、WhisperX、pyannote、Provider Manager 或新的工作流框架。
