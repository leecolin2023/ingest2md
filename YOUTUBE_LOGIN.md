# YouTube 登录与访问诊断

## 设计原则

YouTube 的登录态、JavaScript challenge、播放请求校验是不同问题：

- Cookie：解决账号登录态，以及部分 `Sign in to confirm you're not a bot` 场景。
- Deno / Node + yt-dlp EJS：解决 YouTube JavaScript challenge，不代表已登录。
- 403 / PO Token：属于播放请求校验；不要把它误判为 Cookie 一定失效。

## 推荐配置

优先使用站点独立 Cookie：

```yaml
youtube_cookies_file: ~/.config/ingest2md/youtube-cookies.txt
bilibili_cookies_file: ~/.config/ingest2md/bilibili-cookies.txt
```

旧的 `cookies_file` 继续保留为兼容回退；站点专用配置优先。

Cookie 文件不得提交到 Git，不应通过聊天、邮件或公开渠道转发。Linux/WSL 可执行：

```bash
chmod 600 ~/.config/ingest2md/youtube-cookies.txt
```

## 零额度检测

拿到 Cookie 后先执行：

```bash
ingest2md "https://www.youtube.com/watch?v=VIDEO_ID" \
  --youtube-cookies-file ~/.config/ingest2md/youtube-cookies.txt \
  --check-access
```

该命令只检查：

1. YouTube URL / 元数据是否可访问；
2. Cookie 文件是否为 Netscape 结构且含 YouTube 域；
3. 是否找到可用音频格式；
4. Deno / Node 是否存在且版本满足最低要求。

它不会下载完整音频，也不会调用转写/翻译 API。

## 如何拿到 YouTube 登录 Cookie

`ingest2md` 使用 **Mozilla/Netscape 格式 cookies.txt 文件**。Cookie 本质上等同于登录凭据，不能提交到 Git、粘贴到 issue/聊天，或公开分享。

### 推荐方法：专用无痕会话导出

yt-dlp 当前针对 YouTube 的建议是尽量使用一个独立会话，因为 YouTube 会轮换账号 Cookie。

1. 新开一个无痕/隐私窗口。
2. 在这个窗口登录 YouTube，并确认目标视频可以正常播放。
3. 在**同一个标签页**打开：

```text
https://www.youtube.com/robots.txt
```

4. 使用可信的 Cookie 导出工具，把当前 `youtube.com` 会话导出为 **Netscape / cookies.txt** 格式。Chromium 系浏览器可使用 yt-dlp FAQ 提到的 **Get cookies.txt LOCALLY**；Firefox 可使用兼容的 `cookies.txt` 导出扩展。若要在无痕窗口使用扩展，需要先允许该扩展在无痕/隐私模式运行。
5. 建议保存为：

```text
youtube-cookies.txt
```

6. 导出后立即关闭整个无痕/隐私窗口，**不要继续使用刚才的登录会话**，避免 Cookie 被继续轮换。

> 安装 Cookie 扩展时必须确认来源。yt-dlp FAQ 特别提醒过旧的 **Get cookies.txt**（不是 **Get cookies.txt LOCALLY**）曾被报告存在安全问题。

文件第一行通常应是：

```text
# Netscape HTTP Cookie File
```

或：

```text
# HTTP Cookie File
```

Linux / macOS / WSL 可放到：

```bash
mkdir -p ~/.config/ingest2md
mv ~/Downloads/youtube-cookies.txt ~/.config/ingest2md/youtube-cookies.txt
chmod 600 ~/.config/ingest2md/youtube-cookies.txt
```

Windows 例如：

```text
C:\Users\<你的用户名>\.config\ingest2md\youtube-cookies.txt
```

### 更省事的方法：从普通浏览器配置直接导出

yt-dlp 可以直接读取浏览器 Cookie：

```bash
yt-dlp --cookies-from-browser chrome --cookies youtube-cookies.txt
```

浏览器名称也可以是 `edge`、`firefox`、`brave`、`chromium`、`opera`、`vivaldi`、`safari` 等。

但这个方法要注意：

- 它可能导出**整个浏览器配置中的 Cookie**，不只 YouTube，因此文件更敏感；
- 不适合拿来导出上面专门创建的无痕 YouTube 会话。yt-dlp 文档明确提醒，这种方式通常读取的是浏览器常规配置，而不是刚才的无痕会话。

### Cookie 文件格式检查

`ingest2md` 的 `--check-access` 会检查 Netscape 结构。手工查看时：

- 第一行应类似 `# Netscape HTTP Cookie File`；
- 后续记录通常是 7 列 Tab 分隔；
- 应能看到 `.youtube.com` 等 YouTube 域记录。

如果 yt-dlp 报 `HTTP Error 400: Bad Request`，还应检查文件换行：Windows 通常为 CRLF，Linux/macOS 通常为 LF。

### 导出后先验证，不要直接跑完整转写

```bash
ingest2md "https://www.youtube.com/watch?v=VIDEO_ID" \
  --youtube-cookies-file ~/.config/ingest2md/youtube-cookies.txt \
  --check-access
```

Windows PowerShell：

```powershell
ingest2md "https://www.youtube.com/watch?v=VIDEO_ID" --youtube-cookies-file "C:\Users\<你的用户名>\.config\ingest2md\youtube-cookies.txt" --check-access
```

通过以后再正式执行：

```bash
ingest2md "https://www.youtube.com/watch?v=VIDEO_ID" \
  --youtube-cookies-file ~/.config/ingest2md/youtube-cookies.txt
```

v0.8 会优先尝试平台字幕；有字幕时直接保留原语言，不调用 ASR 或 LLM。只有没有可用字幕时才下载音频，并进入配置的 ASR backend（默认 SenseVoice 本地转写）。

## 错误分类

- `auth`：bot challenge / 登录验证；优先检查 Cookie 和网络出口。
- `cookie`：Cookie 无效或过期；重新导出。
- `rate_limit`：429；降低请求频率或调整网络出口。
- `js`：签名 / nsig / JS challenge；检查 yt-dlp EJS 与 Deno>=2.3 或 Node>=22。
- `playback`：403 / PO Token 类；Cookie 可能仍有效，应检查 player client / PO Token / 网络出口。

## 正式转写

检测通过后再执行正常命令。`--limit-seconds 30` 只限制后续切段/转写时长，当前仍会先下载完整音频；因此不要再用它作为 Cookie 健康检查手段。
