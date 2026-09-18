# ingest2md v0.8.1 Test Report

测试日期：2026-09-18

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
30 passed
```

执行链路：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

PR CI run：

```text
35325059825
```

## v0.8.1 YouTube 获取链路修复

1. 正常 YouTube ingestion 不再前置调用 `probe_video()`；
2. `probe_video()` 只保留给 `--check-access` 的独立音频播放诊断；
3. YouTube 首先直接探测人工/自动字幕；
4. 有字幕时复用字幕探测阶段已经取得的 yt-dlp `info` 作为标题、频道、时长、简介等元数据，不额外发起 metadata/audio probe；
5. 字幕探测与 YouTube 音频下载复用同一套 Cookie、重试、JS runtime 配置；
6. 没有可用字幕或字幕探测失败时，才进入音频下载 → ASR fallback；
7. 新增回归断言：字幕可用时调用 `probe_video`、下载音频或运行 ASR 均视为测试失败；
8. 新增 metadata-from-info 回归，确保字幕路径可以完全复用现有 yt-dlp info。

## v0.8 Local-first 回归

继续覆盖：

- 默认 `asr_backend=sensevoice`；
- `sensevoice / openai / llm` 三种 ASR backend；
- SenseVoice 自己处理 20 秒 WAV；
- OpenAI-compatible backend 自己处理 MP3 与 `/audio/transcriptions`；
- 字幕与 ASR 保持原语言，不强制翻译；
- YouTube/Bilibili subtitle-first；
- YouTube 无字幕时进入 ASR fallback；
- Generic Web → Trafilatura；
- PDF/Office → MarkItDown；
- 小宇宙、本地媒体、分享文案、BV 号与 deferred media 路由；
- Netscape Cookie 与 `--explain`。

## 边界

这次修复的是 **ingest2md 自己的请求顺序与重复请求问题**，不绕过 YouTube 外部的 Cookie、网络出口、bot challenge、PO Token 或播放权限校验。

如果同一环境下裸 yt-dlp 仍返回：

```text
Sign in to confirm you're not a bot
```

则说明 YouTube 访问层仍拒绝当前 session / Cookie / 网络出口组合；v0.8.1 不会伪装成应用层已经解决该问题。

基础 CI 仍不下载真实 YouTube 音频，也不下载 SenseVoice 模型或调用外部付费 API。
