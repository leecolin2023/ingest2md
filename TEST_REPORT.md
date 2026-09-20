# ingest2md v0.8.4 Test Report

测试日期：2026-09-21

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
38 passed
```

执行链路：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

代码回归 CI run：

```text
35545916051
```

## v0.8.4 Douyin browser acquisition

本版把抖音从 DeferredMediaExtractor 中拆出，新增轻量单视频采集能力：

1. `v.douyin.com` 分享短链和 Douyin URL 路由到 `DouyinExtractor`；
2. Playwright 打开真实页面并跟随平台跳转；
3. 仅消费 DOM 已暴露的 `video.currentSrc / video.src / source[src]` 直接 `http(s)` 媒体 URL；
4. 可选读取 Netscape 格式 `douyin_cookies_file`；
5. 下载时复用当前页面 Referer / Cookie，再交给已有 `transcribe_audio()`；
6. 默认继续使用 SenseVoice 本地 ASR；
7. 页面仅暴露 `blob:`、登录墙或没有直接媒体地址时明确失败并提示 Cookie / 本地文件 fallback；
8. 微信视频号仍保持 deferred，不掉入 Generic Web。

## 新增回归

在 v0.8.3 的 34 项基础上新增 4 项：

- 抖音分享短链必须路由到 `DouyinExtractor`，不再进入 DeferredMediaExtractor；
- DOM snapshot 遇到 `blob:` 时能够跳过，并选择可直接下载的 http(s) source；
- DouyinExtractor 能把浏览器解析出的媒体 URL、Referer、Cookie 交给下载器并复用共享 ASR；
- `douyin_cookies_file` 能按 config.yaml 所在目录解析相对路径。

因此当前：

```text
38 passed
```

## 明确保留的边界

本版没有实现：

- `a_bogus` / `X-Bogus` 或其他私有签名算法；
- Douyin 私有 detail API client；
- DouK/TikTokDownloader Sidecar；
- 主页批量、合集、评论、直播；
- 无水印保证；
- Playwright network interception / blob 解码 fallback。

这些能力只有在 DOM 轻量方案真实使用成功率不足、且收益明确时再考虑。

## CI 边界

基础 CI 不真正启动 Playwright 访问抖音，也不下载真实抖音媒体或 SenseVoice 模型。当前测试验证路由、DOM snapshot 选择、Cookie/Referer 传递、ASR pipeline 接续与既有功能回归。真实抖音可用率仍需用公开分享链接做端到端 smoke test。
