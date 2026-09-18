# ingest2md v0.8 Test Report

测试日期：2026-09-18

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
29 passed
```

执行链路：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

CI run：

```text
35303957788
```

## v0.8 新增覆盖

1. 默认 `asr_backend=sensevoice`，基础媒体路径不依赖付费 API；
2. `sensevoice / openai / llm` 三个 ASR backend 能按配置路由；
3. SenseVoice backend 自己选择 20 秒、16kHz 单声道 WAV 切片；
4. OpenAI-compatible backend 自己选择 MP3 切片并调用 `/audio/transcriptions`；
5. 字幕进入 `TranscriptResult` 后保持原语言，不再调用翻译器；
6. YouTube / Bilibili 有字幕时继续跳过 ASR；
7. YouTube 无字幕时进入所选 ASR backend，默认显示为 SenseVoice fallback；
8. v0.7 的 `api_key/base_url/model/candidates/chunk_seconds` 配置可迁移到新的 LLM backend 字段；
9. `translation_model` 与翻译执行链已从 v0.8 配置/运行时移除。

## 既有回归

v0.6 / v0.7 的核心行为继续覆盖：

- 分享文案第一条 URL 与 BV 号规范化；
- 本地媒体路由；
- 抖音 / 微信视频号在 Generic Web 前明确拦截；
- 小宇宙公开页面、`__NEXT_DATA__`、`og:audio` fallback；
- 默认 Markdown 与 JSON opt-in；
- Generic Web → Trafilatura 优先；
- PDF / Office → MarkItDown Adapter；
- `--explain` dry-run；
- YouTube / Bilibili subtitle-first；
- VTT / SRT 解析；
- Cookie 解析与时间段 Markdown。

## CI 边界

基础 CI **不安装 `ingest2md[local-asr]`，也不下载 SenseVoiceSmall 模型**。SenseVoice、OpenAI ASR 与 LLM audio 的 backend 行为通过 mock / fixture 验证，以保持基础 CI 轻量、稳定且不调用外部付费 API。

真实本地 ASR 使用时需要：

```bash
python -m pip install -e ".[local-asr]"
```

并确保系统存在 `ffmpeg` 与 `ffprobe`。首次使用可自动下载 `iic/SenseVoiceSmall`，也可通过 `sensevoice_model_dir` 指向已有模型目录。
