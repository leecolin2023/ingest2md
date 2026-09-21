# ingest2md v0.11.0 Test Report

测试日期：2026-09-21

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
64 passed
```

验证链路：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

已验证的 GitHub Actions run：

```text
35570669327
```

其中 Python 3.12 为 `64 passed in 7.40s`，Python 3.10 同样完整通过安装、compileall、pytest 与 CLI smoke。

## v0.11 核心回归

本版新增的架构回归重点覆盖：

1. **输出防覆盖**：不同 source URL 即使标题相同，也会生成不同的稳定文件名；
2. **Batch metadata 闭环**：`name/tags` 进入最终 Document/Markdown；同一任务的 metadata 变化后，既有 success 会重新进入 pending；
3. **Canonical identity**：不同入口可映射到同一 semantic identity，并复用已有成功产物；
4. **Duplicate 状态**：SQLite 独立记录 `duplicate`，并保留指向已成功任务的输出路径；
5. **自动 retry**：临时 timeout 可按最大尝试次数自动重试，最终成功后不会留下 failed；
6. **媒体缓存**：失败恢复媒体缓存支持 store/get/discard，成功任务默认清理；
7. **Presentation enhancer 边界**：LLM 可以修改 Markdown 展示文本，但原始 `TranscriptResult.segments` 不发生变化；
8. **Batch status**：状态库可以汇总 success/duplicate/failed/pending/running、累计尝试次数和失败类型；
9. **旧能力兼容**：v0.9.3 之前的 55 个回归仍全部通过。

## Online smoke corpus

真实网站可靠性与普通 CI 分离。

`tests_online/` 默认不进入 `pytest` testpaths，需要显式提供真实测试源后手工运行：

```bash
python -m pytest tests_online -q
```

覆盖入口包括 Generic Web、YouTube、Bilibili、小宇宙、抖音。未配置的来源自动 skip，Cookie/真实账号信息不进入仓库或 GitHub Actions。

因此：

> **64 passed 代表工程正确性，不代表 64 个真实平台场景永远在线可用。**

平台 Adapter 发生明显变化或发布大版本时，再运行 online smoke corpus，用于区分代码回归与平台行为变化。

## 保持不变的边界

- Batch 继续串行，不引入 worker/scheduler；
- 不引入 ProviderManager / PipelineEngine / 动态 Plugin Framework；
- 不引入 VAD、speaker diarization、WhisperX、pyannote；
- Markdown 仍是 canonical output；
- SRT/JSON 仍基于原始 TranscriptResult；
- Transcript Enhancer 默认关闭；
- 失败媒体缓存只服务 retry durability，不演化为通用 HTTP/cache layer。
