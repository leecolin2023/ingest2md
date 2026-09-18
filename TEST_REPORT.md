# ingest2md v0.8.2 Test Report

测试日期：2026-09-18

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
32 passed
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
35332827238
```

## v0.8.2 Maintenance cleanup

本版不新增产品能力，不改变用户可见行为，重点消除双重维护点：

1. 本地媒体与网络媒体统一复用 `retain_media()`，本地媒体通过 `retained_filename` 保持原来的 `source_media.<ext>` 命名；
2. 新增共享 `parse_netscape_cookie_file()`，Playwright Cookie 与 YouTube Cookie 校验均基于同一 parser；
3. Extractor registry 同时维护路由顺序与 Settings 注入；CLI 不再维护一份 Bilibili/YouTube/Xiaoyuzhou/LocalMedia/Zhihu/Xiaohongshu 类型名单；
4. YouTube 的严格音频访问诊断改名为 `probe_playback_access()`，降低被误用到正常 ingestion 主链路的风险；
5. Web/Zhihu/Xiaohongshu/Xiaoyuzhou/media downloader/Bilibili 统一使用 `DEFAULT_USER_AGENT`；
6. Generic Web/Xiaohongshu/Xiaoyuzhou 的 HTML meta 读取统一到 `htmlutils.meta_content()`。

## 新增回归

新增 2 项针对维护风险的测试：

- shared Netscape parser 同时驱动 Playwright Cookie 转换与 YouTube Cookie 校验，包括 `#HttpOnly_`；
- registry 能在不依赖 CLI 类型判断的情况下向 YouTubeExtractor 注入同一个 Settings 对象。

因此测试数从 v0.8.1 的 30 项增加为：

```text
32 passed
```

## 保持不动的边界

本版刻意没有引入：

- VideoSubtitleMixin；
- ASR backend 公共 chunk-loop 抽象；
- generic provider headers 配置框架；
- 对 v0.7 legacy config migration 的删除；
- 对 subtitle wrapper / SenseVoice defensive calls / Document original_* 字段的清理。

这些仍保留到确有维护收益时再处理，避免为了 DRY 引入更重抽象。

## CI 边界

基础 CI 仍不下载真实 YouTube/Bilibili 媒体，不下载 SenseVoiceSmall 模型，也不调用外部付费 API。当前测试验证的是路由、解析、backend 契约和此次 maintenance cleanup 的行为不变性。
