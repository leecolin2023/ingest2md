# ingest2md v0.6 Test Report

测试日期：2026-09-17

## 结果

```text
16 passed
```

执行命令：

```bash
PYTHONPATH=. pytest -q
```

## 本轮覆盖

1. 抖音整段分享文案能提取第一条 URL；
2. 普通纯 URL 保持 v0.4 行为；
3. Bilibili BV 号保持兼容；
4. 已存在 `.mp4` 能进入 Local Media；
5. 不存在的 `missing.mp4` 不会误判为本地媒体；
6. 抖音在 Generic Web 前被明确拦截；
7. 微信视频号在 Generic Web 前被明确拦截；
8. 小宇宙 episode 进入专用 Extractor；
9. 小宇宙 Fixture 可从 `__NEXT_DATA__` 取得标题、播客、Show Notes、时长、音频 URL；
10. 小宇宙可回退到 `og:title / og:description / og:audio`；
11. 小宇宙 Extractor 实际调用现有 `transcribe_audio()`；
12. 默认只输出 Markdown；
13. `--formats md,json` 仍是显式 opt-in；
14. Generic Web 正文解析回归；
15. 视频时间段 Markdown 回归；
16. Netscape Cookie 解析回归。

## 关于“原来的 9 项测试”

本次上传的 `ingest2md(1).zip` 只包含 `ingest2md/` Python 包，没有上一版 `tests/`、`pyproject.toml` 或 `TEST_REPORT.md`，所以无法直接逐文件重跑原测试集合。

本轮采取的做法是：不重构原有微信、知乎、小红书、Bilibili、YouTube核心实现，同时把 v0.4 README 所描述的关键公共行为纳入新的回归测试。

## 未做在线端到端转写

执行环境无法直接访问互联网，因此没有在本地测试进程中真实下载小宇宙音频、调用转写 API。小宇宙页面结构通过公开页面与公开实现资料进行了外部核对；本地自动化测试使用 Fixture 和 mock 验证解析与调用链。
