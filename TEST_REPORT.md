# ingest2md v0.10.1 Test Report

功能代码验证基线：`feat/bilibili-resilient-acquisition@1bfa1a2e3dc262eaf25efce396cf447cb94c6439`

GitHub Actions run：`37014142349`

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

当前测试文件包含 **67 个 test functions**，Python 3.10 / 3.12 的 pytest 与 CLI 校验均通过。

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
- Bilibili 官方 view API 元信息优先、yt-dlp fallback；
- Bilibili 分 P 语义错误不会被 fallback 掩盖；
- Bilibili yt-dlp fallback 复用 Cookie 与 Referer / User-Agent；
- Bilibili 音频续传、重试、fragment retry、socket timeout；
- Bilibili ASR fallback 注入 source-aware NormalizationHints；
- 小宇宙公开 episode、Show Notes、音频完整性校验与 source hints；
- 抖音详情响应 / DOM / 浏览器网络媒体候选顺序与无效媒体剔除；
- MarkItDown document delegation。

### Transcription

- 默认 SenseVoice local-first；
- 三种 ASR backend factory；
- backend 自己拥有预处理与 chunking；
- Markdown 阅读窗口与底层 ASR segment 解耦；
- Transcript Normalization 默认 `basic`；
- Raw ASR 保留；
- LLM normalization 失败回退 basic；
- segment 数量、顺序与时间戳 invariants；
- 平台原生字幕不做二次 Normalization。

### Batch / Runtime

- TXT / CSV / JSONL manifest；
- TXT 自由文本多 Reference scanner；
- IngestionEngine 作为 single / batch 共用核心；
- SQLite resume / retry；
- 单任务失败隔离；
- RuntimeContext 懒加载并复用 ASR backend；
- SenseVoice 模型跨任务复用；
- Chromium process 复用且 BrowserContext 按任务隔离。

## v0.10.1 回归重点

- Bilibili view API 不再是元信息单点故障；
- fallback 只处理获取失败，不吞掉“第 N P 不存在”等语义错误；
- yt-dlp fallback 与现有字幕 / 音频链路共享 Cookie 与请求头；
- 音频下载失败策略仍是有限重试，而不是无限重试；
- 字幕优先原则不变；
- 只有无字幕进入 ASR 时才注入 Bilibili NormalizationHints；
- 没有新增私有 API、签名逆向、Provider Manager 或平台专用转写实现。

## 测试不代表什么

这些测试主要验证内部行为与回归，不等于对第三方网站的实时可用性承诺。

Bilibili 仍可能因为登录 / Cookie、地区限制、平台风控、yt-dlp 兼容性、CDN 状态或页面 / API 策略变化而失败。
