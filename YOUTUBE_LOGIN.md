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

## Cookie 导出建议

用独立的浏览器隐私/无痕会话登录 YouTube，确认目标视频可播放后导出 Netscape 格式 Cookie；导出后关闭该独立会话，避免继续使用同一会话导致 Cookie 轮换。仅导出 YouTube/Google 登录所需 Cookie，妥善保管。

## 错误分类

- `auth`：bot challenge / 登录验证；优先检查 Cookie 和网络出口。
- `cookie`：Cookie 无效或过期；重新导出。
- `rate_limit`：429；降低请求频率或调整网络出口。
- `js`：签名 / nsig / JS challenge；检查 yt-dlp EJS 与 Deno>=2.3 或 Node>=22。
- `playback`：403 / PO Token 类；Cookie 可能仍有效，应检查 player client / PO Token / 网络出口。

## 正式转写

检测通过后再执行正常命令。`--limit-seconds 30` 只限制后续切段/转写时长，当前仍会先下载完整音频；因此不要再用它作为 Cookie 健康检查手段。
