# ingest2md v0.7 Test Report

测试日期：2026-09-18

## 结果

```text
24 passed
```

执行命令：

```bash
python -m pytest -q
python -m compileall -q ingest2md
```

## v0.7 新增覆盖

1. 本地 PDF 与远程 DOCX 在 Generic Web 之前进入 Document Adapter；
2. Document Adapter 将文档委托给 Microsoft MarkItDown，并保持统一 Document 输出；
3. `--explain` 能说明 YouTube 路由与 subtitle-first 计划，且不执行抓取；
4. Generic Web 优先使用 Trafilatura；
5. VTT/SRT 字幕可解析并进入统一 TranscriptResult；
6. YouTube 有字幕时跳过 ASR；
7. YouTube 无字幕时进入音频 + ASR fallback；
8. Bilibili 有字幕时跳过 ASR。

## 既有回归

原有 16 项 v0.6 测试继续通过，覆盖分享文案、BV 号、本地媒体、抖音/视频号拦截、小宇宙解析、默认 Markdown、JSON opt-in、Generic Web 基础回归、视频时间段与 Cookie 解析。

## 在线端到端边界

当前执行环境不能直接访问互联网，因此本地自动化测试通过 fixture / mock 验证字幕优先、ASR fallback、MarkItDown 委托与 Trafilatura 路由。真实依赖安装与完整测试继续由 GitHub Actions 的联网环境验证。
