# ingest2md v0.9.1 Test Report

测试日期：2026-09-21

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
48 passed
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
35555458967
```

## v0.9.0 Batch Foundation

- 单条执行核心抽到 `IngestionEngine.ingest_one()`；
- legacy `ingest2md <source>` 保持兼容；
- 新增 `ingest2md batch <manifest>`；
- TXT / CSV / JSONL 统一加载为 BatchItem；
- SQLite TaskStore 保存 `pending/running/success/failed`；
- 支持 `--resume`、`--take`、`--retry-failed`；
- 同一配置指纹下按规范化输入去重，成功后记录 canonical key；
- v0.9.0 保持串行，不引入 worker/pipeline 框架。

## v0.9.1 Long-lived Runtime

- RuntimeContext 与 SQLite TaskStore 分离：前者只管执行资源，后者只管 batch 状态；
- 同一 RuntimeContext 懒加载并复用一个 ASR backend；
- SenseVoiceBackend 缓存已初始化 ONNX 模型，多媒体任务不重复加载；
- BrowserRuntime 复用一个 Playwright/Chromium 进程；
- 每条浏览器任务仍建立独立 BrowserContext 并及时关闭；
- Bilibili / YouTube / 小宇宙 / 本地媒体 / 抖音共享 ASR runtime；
- 知乎 / 小红书 / 抖音 / Generic Web browser fallback 共享 Chromium runtime；
- 没有 RuntimeContext 时继续走原有单项资源路径，保持 Adapter 独立可用。

## 新增回归重点

- TXT / CSV / JSONL loader；
- SQLite 去重、resume、retry-failed；
- BatchRunner 单任务失败隔离；
- IngestionEngine 单条核心；
- RuntimeContext 的 ASR backend lazy reuse；
- BrowserContext 在共享 BrowserRuntime 上逐任务创建并关闭；
- SenseVoiceBackend 连续处理两个媒体时模型只初始化一次；
- registry 能同时注入 Settings 与 Runtime。

## 当前边界

本版仍没有：

- task 并发；
- fetch/asr 分阶段队列；
- ASR/browser semaphore；
- HTTP Client 全局连接池；
- 平台限流器；
- 复杂指数退避和 typed exception hierarchy。

这些能力应在真实批量 workload 有数据后再决定，避免提前建设重型任务平台。
