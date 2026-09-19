---
name: ingest2md
description: 把网页链接、App 分享文案和本地音视频转换为本地、可直接阅读并可批量交给 LLM 的 Markdown 语料。支持微信公众号、知乎、小红书、Bilibili、YouTube、小宇宙、普通网页、本地音视频和可选 PDF/Office 文档；抖音/视频号可识别但暂不自动获取媒体。
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
- B站/YouTube：优先使用平台人工/自动字幕；有字幕直接保留原语言，没有字幕才进入 ASR。
- 小宇宙：节目简介 / Show Notes + 公开音频转写；默认使用本地 SenseVoice，保留原语言。
- 本地音视频：默认 `SenseVoiceBackend` 本地转写；也可显式选择 OpenAI-compatible ASR 或多模态 LLM audio。Backend 自己决定切片格式与时长。
- 普通网页：HTTP 获取后优先用 Trafilatura 提取正文，必要时才用浏览器 fallback。
- PDF/DOCX/PPTX/XLSX：交给可选的 Microsoft MarkItDown Adapter，不自行实现文档解析。

## v0.8.3 本地 ASR 性能规则

- SenseVoice 默认 `sensevoice_chunk_seconds=30`、`sensevoice_batch_size=4`；
- SenseVoice 必须真正批量传入多个 WAV 文件，不能只把 `batch_size` 传给模型后仍逐片调用；
- 音频切片使用一次 ffmpeg segment 完成，避免按 chunk 重复启动进程；
- 可通过 `--sensevoice-batch-size 8` 做本机 benchmark，但不要假设 batch 越大一定越快；
- 性能日志应保留 preprocess / model setup / inference / total / RTF，便于后续基于实测优化。

## v0.8 音视频规则

- 默认 `asr_backend=sensevoice`，不要求任何付费 API。
- SenseVoice 依赖按需安装：`pip install -e ".[local-asr]"`。
- 字幕与 ASR 结果保持原语言，不做自动中文翻译。
- `openai` backend 仅负责 OpenAI-compatible `/audio/transcriptions`。
- `llm` backend 负责兼容 `chat/responses + input_audio` 的多模态模型；Opencode 只是默认示例配置。
- 不建立 Provider Manager / Registry；`transcribe_audio()` 只选 backend，各 backend 自己做预处理与切片。

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

## 路由解释

```bash
ingest2md "<Content Reference>" --explain
```

只解释输入类型、识别来源、Adapter 与处理计划；不抓取、不下载、不调用模型，也不生成文件。

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
- 小宇宙与本地媒体都复用 `transcribe_audio()`；ASR backend 自己负责切片，不新增 MediaProviderManager / Resolver Registry。
- 不把采集阶段变成总结阶段：默认尽量保留正文，后续分析交给 LLM。
- 对不稳定网站，优先返回可读的部分结果/清晰错误，不建设重型审计产物。
- 已识别但未稳定支持的平台必须明确失败，不得悄悄降级成 Generic Web。
- 详细安装、配置、边界见 `README.md`。
