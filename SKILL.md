---
name: ingest2md
description: 把网页链接、App 分享文案和本地音视频转换为本地、可直接阅读并可批量交给 LLM 的 Markdown 语料。支持微信公众号、知乎、小红书、Bilibili、YouTube、小宇宙、普通网页和本地音视频；抖音/视频号可识别但暂不自动获取媒体。
---

# ingest2md — Content Reference → LLM Markdown Corpus

## 何时使用

当用户希望“读取 / 保存 / 归档 / 整理 / 分析”一个在线内容或音视频，并希望后续让人或大模型继续阅读时使用。

支持的输入不再局限于 URL：

- 微信公众号文章；
- 知乎问题或回答 URL：默认按**问题导向**，获取问题和尽可能多回答；
- 小红书笔记；
- Bilibili 单视频/分P或 BV 号；
- YouTube 单视频；
- 小宇宙单集；
- 普通 http/https 网页；
- App 分享文案：自动取其中第一条 http(s) URL；
- 本地 MP3/M4A/WAV/AAC/FLAC/OGG/OPUS；
- 本地 MP4/MKV/MOV/WebM/AVI/M4V；
- 播客、访谈、会议录音等希望转成大模型语料的本地媒体。

## 默认调用

```bash
ingest2md "<Content Reference>" -o <输出目录>
```

例如：

```bash
ingest2md "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e" -o archive
ingest2md "6.48 复制打开抖音…… https://v.douyin.com/akR8LCIaTMI/ ……" -o archive
ingest2md "./meeting.m4a" -o archive
ingest2md "D:\Downloads\video.mp4" --limit-seconds 60 -o archive
```

默认只有 Markdown。不要为了“结构化”主动生成 JSON、raw HTML、manifest、下载媒体等额外产物。

## 平台语义

- 微信：文章正文 + 本地图片。
- 知乎：问题 + 尽可能多回答，合并成一个 Markdown；不是只保存当前回答。
- 小红书：正文 + 当前可取得的笔记图片；默认不跑 OCR/Vision。
- B站/YouTube：音频按原语言转写，再翻译为简体中文。
- 小宇宙：节目简介 / Show Notes + 公开音频转写；转写正文为简体中文。
- 本地音视频：直接复用媒体切片 → 原语言转写 → 中文翻译链路。
- 普通网页：提取主要正文。

## Content Reference 规则

输入规范化顺序：

1. 如果整段输入本身是**真实存在的本地文件**，按 Local Media 处理；
2. 否则如果是 BV 号，规范化成 Bilibili URL；
3. 否则从分享文案中提取第一条 `http(s)` URL；
4. 否则按普通 URL 兼容规则处理。

不要因为字符串以 `.mp4` / `.mp3` 结尾，就假定它是本地文件；文件必须真实存在。

## 已识别但未稳定支持的平台

对抖音和微信视频号，不要让 Generic Web 假装抓取成功。

如果识别到：

```text
v.douyin.com
douyin.com
weixin.qq.com/sph/
channels.weixin.qq.com
```

应明确提示：

```text
已识别来源：抖音视频
当前版本暂未接入稳定的媒体获取方式。
建议下载视频后执行：
ingest2md "/path/to/douyin.mp4"
```

视频号同理。

核心原则：

> 能以轻量、稳定方式接入的就接；需要维护私有签名、特殊登录服务、解密链路、专用 Sidecar 的来源先不做。

## 小宇宙规则

只处理公开单集：

```text
https://www.xiaoyuzhoufm.com/episode/<24位episode id>
```

解析优先级：

1. `__NEXT_DATA__` 中的 episode；
2. `og:title / og:description / og:audio`；
3. `media.xyzcdn.net` 音频 URL 正则兜底。

取得公开音频后，下载到临时目录并交给现有 `transcribe_audio()`。不要建立第二套播客转写框架。

最终正文应保持：

```markdown
## 节目简介
...

## Show Notes
...

## 转写正文

### 00:00–05:00
...
```

默认不要生成 `episode.json`、`raw.html`、`audio.m4a` 等调试/中间产物。

## 需要登录态时

Cookie 使用 Netscape 格式：

```bash
ingest2md "<知乎URL>" --zhihu-cookies-file zhihu-cookies.txt
ingest2md "<小红书URL>" --xiaohongshu-cookies-file xhs-cookies.txt
ingest2md "<YouTubeURL>" --youtube-cookies-file youtube-cookies.txt
```

## 额外产物只有用户需要时才开

```bash
--formats md,srt
--formats md,json
--formats md,txt
--keep-audio
--keep-chunks
```

本地媒体使用 `--keep-audio` 时保存的是输入媒体副本 `source_media.<ext>`。

## 规则

- 输入尽量用引号完整包裹，特别是分享文案和 Windows 路径。
- 知乎默认“尽可能多”，但不承诺绝对抓全；如果用户只想快速验证，可加 `--max-answers 10`。
- 小宇宙与本地媒体都复用已有转写服务，不新增 MediaProviderManager / Resolver Registry。
- 不把采集阶段变成总结阶段：默认尽量保留正文，后续分析交给 LLM。
- 对不稳定网站，优先返回可读的部分结果/清晰错误，不建设重型审计产物。
- 已识别但未稳定支持的平台必须明确失败，不得悄悄降级成 Generic Web。
- 详细安装、配置、边界见 `README.md`。
