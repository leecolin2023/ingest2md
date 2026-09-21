# ingest2md v0.9.3 Test Report

测试日期：2026-09-21

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
55 passed
```

执行链路：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

首轮 v0.9.3 CI run：

```text
35563505760
```

## v0.9.3 Podcast / Long-form Transcript

本版把“模型推理切片”和“最终 Markdown 阅读结构”正式解耦，并优先增强小宇宙长音频：

1. 小宇宙音频下载完成后先调用现有 `probe_media_info()`；
2. 无音轨、时长无效、或实际时长明显短于页面 episode duration 时，在 ASR 前直接失败；
3. 新增 `transcript_window_seconds=300`，只控制 Markdown 展示窗口；
4. SenseVoice 仍保持自己的 30 秒 WAV chunk，不因 Markdown 展示粒度而变化；
5. 通用 `render_markdown()` 将底层 segments 聚合为可读时间窗口；
6. 小宇宙 Show Notes 中的 `MM:SS` / `H:MM:SS` 时间点会解析成语义章节；
7. 支持普通 Markdown 行、列表和时间戳链接形式；
8. 有章节时优先按章节组织转写；没有章节时自动回退到通用时间窗口；
9. SRT / JSON 继续基于原始 TranscriptResult segments，不因 Markdown 聚合而丢失时间信息。

## 新增回归重点

- 30 秒 ASR segments 能聚合成 5 分钟 Markdown 阅读块；
- 最后一段不足 5 分钟时仍保留真实结束时间；
- Show Notes 能解析 `01:21`、链接式 `[15:16](...)`、`1:02:03`；
- chapter renderer 会生成“开场 + Show Notes 章节”；
- 下载音频明显短于页面时长时，必须在 ASR 前失败；
- 既有小宇宙公开页面解析和 shared transcription 仍正常；
- Bilibili / YouTube / 本地媒体 / 抖音也统一使用 transcript presentation window；
- 新配置项进入 batch config fingerprint，展示规则变化可触发重新处理。

## 保持不变的边界

- 不改变 SenseVoice / OpenAI ASR / LLM audio backend 的切片策略；
- 不引入第二套小宇宙转写框架；
- 不使用 LLM 猜测章节标题，章节语义只来自平台 Show Notes；
- 不引入 VAD、speaker diarization、WhisperX、pyannote 等重型依赖；
- 不默认生成 SRT；SRT 仍是显式 opt-in 的互操作格式；
- Markdown 是面向人和 LLM 的 canonical output，底层 TranscriptResult 仍保留原始 segment 时间。

这使长播客从“ASR 原始切片堆叠”向“结构化、可定位的长文本语料”前进一步，同时保持现有轻量架构。
