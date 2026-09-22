# ingest2md v0.9.3 Test Report

测试基线：`main@1e4234de8fd420d0eed99c0cd8e041437ad419ee`

GitHub Actions run：`35563648583`

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

当前测试集：

```text
55 passed
```

## 覆盖重点

当前 55 个测试主要覆盖以下产品边界：

### Reference / Router

- App 分享文本 URL 提取；
- BV 号规范化；
- 本地文件只在真实存在时路由；
- 特定平台优先于 Generic Web；
- 微信视频号 deferred 路由；
- `--explain` dry-run。

### Source adapters

- 微信 / 普通网页解析基础能力；
- 知乎 / 小红书相关路由与解析辅助；
- YouTube 字幕优先与 ASR fallback；
- Bilibili 字幕优先；
- 小宇宙公开 episode 解析、Show Notes 章节与音频完整性校验；
- 抖音浏览器媒体候选、详情响应优先级、无效短媒体剔除；
- MarkItDown document delegation。

### Transcription

- 默认 SenseVoice local-first；
- 三种 ASR backend factory；
- SenseVoice 自己拥有 WAV chunking；
- true multi-file batch inference；
- 单次 ffmpeg segment；
- OpenAI-compatible backend 自己拥有 MP3 chunking；
- Markdown 阅读窗口与底层 ASR segment 解耦；
- SRT / JSON 仍使用原始 TranscriptResult 时间信息。

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

在线平台仍可能因为以下因素失败：

- 登录 / Cookie 失效；
- 反爬或人机校验；
- YouTube JS challenge / PO Token / 网络出口；
- 页面结构变化；
- 地区限制或平台临时策略。

因此文档中的“已接入”表示项目已有明确处理链路，并不表示所有公开 URL 在所有网络环境下都必然成功。

## v0.9.3 回归重点

- 小宇宙下载音频在 ASR 前校验音轨与明显截断；
- `transcript_window_seconds` 只控制 Markdown 展示，不改变 backend chunk；
- 固定窗口可聚合 30 秒 ASR segment；
- Show Notes 支持 `MM:SS`、`H:MM:SS` 与链接式时间点；
- 有语义章节时按章节展示，无章节时回退固定窗口；
- Bilibili / YouTube / 本地媒体 / 抖音继续复用统一 transcript presentation。
