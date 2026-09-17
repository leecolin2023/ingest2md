# url2md — 把你看到和听到的内容变成 LLM 可读 Markdown

`url2md` 是一个轻量的多来源内容采集工具。输入网页链接、App 分享文案或本地音视频，它尽可能提取正文、回答、图片信息或音视频转写，并整理成**人能直接阅读、后续能批量交给大模型处理的本地 Markdown**。

设计原则：

> **输入端尽量强，输出端尽量简单；抓得丰富，存得轻。**

默认只生成 Markdown。只有图片需要本地化时才附带 `images/`；JSON、SRT、TXT、媒体副本和切片都必须显式请求。

v0.5 的边界也很明确：**优先扩大低成本、高价值的信息入口；如果某个平台需要复杂登录态、私有签名、解密或专用基础设施才能稳定支持，则先识别、明确提示，但不强行接入。**

## v0.5 新增

1. **小宇宙 Podcast**：单集页面 → 节目简介 / Show Notes → 公开音频 → 原语言转写 → 中文翻译 → 一个 Markdown。
2. **本地音视频**：支持常见音频、视频文件直接进入现有转写链路。
3. **Content Reference 输入**：CLI 输入从单纯 URL 扩展为 URL、App 分享文案中的 URL、本地文件、B站 BV 号。
4. **抖音 / 微信视频号明确拦截**：能识别来源，但当前不做不稳定的自动媒体下载；不会再掉进 Generic Web 假装抓取成功。

## 支持内容

| 来源 | 状态 | 默认采集语义 | 默认输出 |
|---|---|---|---|
| 微信公众号 | ✅ | 单篇文章 | Markdown + `images/` |
| 知乎 | ✅ | **一个问题 + 尽可能多的回答** | 单个 Markdown |
| 小红书 | ✅ 轻量 | 单篇笔记正文 + 可取得图片 | Markdown + `images/`（有图片时） |
| Bilibili | ✅ | 单视频/分P → 原语言转写 → 中文 | 单个 Markdown |
| YouTube | ✅ | 单视频 → 原语言转写 → 中文 | 单个 Markdown |
| **小宇宙** | **✅ v0.5** | Show Notes + 播客转写 | 单个 Markdown |
| **本地音视频** | **✅ v0.5** | 本地媒体 → 原语言转写 → 中文 | 单个 Markdown |
| 普通网页 | ✅ | 主要正文 | 单个 Markdown |
| 抖音 | ⏸ | 自动识别；媒体下载暂缓 | 明确提示改走本地文件 |
| 微信视频号 | ⏸ | 自动识别；媒体下载暂缓 | 明确提示改走本地文件 |

知乎问题 URL 和某个回答 URL 都会按“问题导向”处理：定位到所属问题，把当前可获取的回答尽量收进同一个 Markdown。

## 安装

Python 3.10+：

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install -e .
python -m playwright install chromium
```

微信首次使用还需要：

```bash
python -m camoufox fetch
```

音视频通道需要 `ffmpeg` 与 `ffprobe`。YouTube 建议安装当前版 Deno 或 Node.js；遇到登录/机器人校验时提供 Cookie。

## 输入已经不是只有 URL

v0.5 把输入统一为：

```text
Content Reference
= URL
| 分享文案中的 URL
| 本地媒体路径
| BV号
```

下面这些都可以直接使用：

```bash
# 普通 URL
url2md "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e"

# 整段 App 分享文本：会提取第一条 http(s) URL
url2md "6.48 复制打开抖音，看看某个作品 https://v.douyin.com/akR8LCIaTMI/ 其他分享口令"

# 本地音频
url2md "./podcast.m4a"

# 本地视频
url2md "D:\Downloads\douyin.mp4"

# B站 BV 号
url2md "BV1xx411c7mD"

# 快速测试前一分钟
url2md "./video.mp4" --limit-seconds 60
```

### 本地媒体格式

音频：`.mp3 .m4a .wav .aac .flac .ogg .opus`

视频：`.mp4 .mkv .mov .webm .avi .m4v`

只有**真实存在的文件**才会被判定为本地媒体。像 `missing.mp4` 这样的不存在路径不会误进入 Local Media。

## 最常用命令

```bash
# 微信
url2md "https://mp.weixin.qq.com/s/xxxx" -o archive

# 知乎：默认按问题抓尽可能多回答
url2md "https://www.zhihu.com/question/2083802170001044893" -o archive

# 只想快速抓前 10 个回答
url2md "https://www.zhihu.com/question/2083802170001044893" --max-answers 10 -o archive

# 小红书
url2md "https://www.xiaohongshu.com/explore/xxxx" -o archive

# 普通网页
url2md "https://example.com/article" -o archive

# B站 / YouTube / 小宇宙 / 本地音视频（需要 OPENCODE_API_KEY）
url2md "https://www.bilibili.com/video/BVxxxxxxxxxx" -o archive
url2md "https://www.youtube.com/watch?v=xxxxxxxxxxx" -o archive
url2md "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e" -o archive
url2md "./meeting.mp3" -o archive
```

## 抖音与微信视频号：识别，但暂不自动下载

v0.5 会在 Generic Web 之前识别这些链接，例如：

```text
v.douyin.com
douyin.com
weixin.qq.com/sph/
channels.weixin.qq.com
```

程序会明确返回：

```text
已识别来源：抖音视频
当前版本暂未接入稳定的媒体获取方式。
建议下载视频后执行：
url2md "/path/to/douyin.mp4"
```

视频号同理。

这样可以避免“网页抓到一点壳内容，就生成一个看似成功但没有价值的 Markdown”。如果之后能找到无需长期维护签名、登录服务或 Sidecar 的稳定公开入口，再把媒体获取接进来。

## 小宇宙处理方式

小宇宙单集只接入公开页面，不依赖私有登录 API。解析顺序：

```text
公开 episode 页面
 ↓
优先读取 __NEXT_DATA__ 中的 episode 数据
 ↓
失败则读取 og:title / og:description / og:audio
 ↓
音频 URL 再提供 media.xyzcdn.net 正则兜底
 ↓
HTTP 流式下载到临时目录
 ↓
复用现有 transcribe_audio()
 ↓
Show Notes + 中文转写 → 一个 Markdown
```

最终 Markdown 形态：

```markdown
# Vol.1 AI最前沿的人已经不聊大模型了

> **来源**: 小宇宙
> **播客**: 易论AI
> **时长**: 1小时33分钟
> 原文链接: https://www.xiaoyuzhoufm.com/episode/...

---

## 节目简介

……

## Show Notes

- 01:21 AI落地……
- 15:16 ……

## 转写正文

### 00:00–05:00

……

### 05:00–10:00

……
```

默认不会留下 `episode.json`、`raw.html`、下载音频或切片；这些都只在明确请求附加产物时保留。

## 本地音视频处理方式

本地音频和视频不新建转写框架，直接复用现有链路：

```text
本地文件
 ↓
ffmpeg / ffprobe
 ↓
切片
 ↓
原语言转写
 ↓
简体中文翻译
 ↓
Markdown
```

视频文件会由 ffmpeg 在切片时忽略画面，只处理音轨。

`--keep-audio` 对网络视频/播客仍保留下载音频；对本地媒体则保留一份 `source_media.<ext>` 副本。`--keep-chunks` 会保留 MP3 切片。

## 输出规则：默认只有一个主 Markdown

文本型内容默认直接落在输出根目录：

```text
archive/
├── 如何评价某问题__2083802170001044893.md
├── 某篇普通网页文章.md
├── 某个YouTube视频__VIDEO_ID.md
└── 本地会议录音.md
```

如果内容带本地图片、你要求保留媒体/切片，或者显式要求附加格式，则相关文件收进一个目录：

```text
archive/
└── 某个内容/
    ├── 某个内容.md
    ├── document.json       # 仅 --formats md,json
    ├── transcript.srt      # 仅 --formats md,srt 且有转写
    ├── source_media.mp4    # 本地媒体 + --keep-audio
    └── chunks/             # 仅 --keep-chunks
```

## 额外格式全部 opt-in

默认：

```text
formats: [md]
```

需要时才指定：

```bash
url2md "<video-or-podcast>" --formats md,srt
url2md "<url>" --formats md,json
url2md "<url>" --formats md,txt
url2md "./video.mp4" --keep-audio --keep-chunks
```

支持 `md,txt,srt,json`。`srt` 只在存在转写结果时输出。

## 知乎实现策略

知乎当前网页/API 对匿名自动化访问并不稳定。项目继续采用 v0.4 的轻量策略：真实浏览器打开问题页、展开回答、持续滚动、按回答 ID 去重，多轮不再新增后停止。

优点是实现简单、与页面阅读行为接近、不需要维护私有 API 签名；代价是**不承诺抓全**。需要登录时，用 `--zhihu-cookies-file` 提供 Netscape Cookie。

## 小红书当前边界

小红书仍是“轻量可用版”：抓页面可见正文、下载当前能定位到的笔记图片，默认不调用 OCR / Vision；小红书视频暂不自动转写。

## 普通网页

普通网页先用 HTTP 直接获取并选择最像正文的 `article/main/content` 区域；如果正文过短或 HTTP 获取失败，再退回 Playwright 浏览器渲染。

Generic Web 永远排在更具体的平台之后。v0.5 路由优先级大致为：

```text
已识别但暂缓的平台
→ 本地媒体
→ 微信 / B站 / YouTube / 小宇宙 / 知乎 / 小红书
→ Generic Web
```

## 视频 / 播客转写

B站、YouTube、小宇宙和本地媒体共用核心转写服务：

```text
媒体输入 → ffmpeg 切段 → 原语言转写 → 中文翻译 → Markdown
```

Markdown 默认按切段时间组织：

```markdown
### 00:00–05:00
……

### 05:00–10:00
……
```

## Cookie

YouTube 登录、Cookie、JS Runtime 与 403/PO Token 的详细诊断见 [`YOUTUBE_LOGIN.md`](YOUTUBE_LOGIN.md)。

Cookie 统一使用 Netscape 格式：

```bash
url2md "<知乎URL>" --zhihu-cookies-file zhihu-cookies.txt
url2md "<小红书URL>" --xiaohongshu-cookies-file xhs-cookies.txt
url2md "<YouTubeURL>" --youtube-cookies-file youtube-cookies.txt
```

## 配置

复制 `config.example.yaml` 为 `config.yaml`。优先级：

```text
CLI 显式参数 > OPENCODE_API_KEY 环境变量 > config.yaml > 默认值
```

核心参数：

| 参数 | 默认 |
|---|---|
| `-o / --output` | `./output` |
| `--formats` | `md` |
| `--max-answers` | `0`，知乎尽可能多 |
| `--chunk-seconds` | `300` |
| `--limit-seconds` | `0`，完整媒体 |
| `--keep-audio` | `false` |
| `--keep-chunks` | `false` |

## 代码结构

```text
url2md/
├── cli.py
├── config.py
├── model.py
├── router.py
├── urlutils.py                 # Content Reference 规范化 / 分享文案 URL 提取
├── browser.py
├── htmlutils.py
├── extractors/
│   ├── base.py
│   ├── deferred_media.py      # NEW: 抖音/视频号识别但暂缓
│   ├── local_media.py         # NEW
│   ├── xiaoyuzhou.py          # NEW
│   ├── wechat.py
│   ├── zhihu.py
│   ├── xiaohongshu.py
│   ├── web.py
│   ├── bilibili.py
│   ├── youtube.py
│   └── video.py
├── media/
│   ├── audio.py
│   ├── bilibili.py
│   ├── youtube.py
│   └── download.py            # NEW: 通用 HTTP 流式下载
└── transcription/
    └── ...                     # 不重构
```

核心仍然保持简单：

```text
输入
 ↓
URL / 分享文案 / 本地路径 / BV 号规范化
 ↓
Router
 ↓
平台 Extractor
 ↓
Document
 ↓
Markdown Writer
```

没有引入 `MediaProviderManager`、Resolver Registry、manifest 或新的媒体抽象层。

## 测试

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

v0.5 当前随包新增 16 项回归/增量测试，覆盖：

- 分享文案提取第一条 URL；
- 普通 URL 与 BV 号兼容；
- 本地媒体存在/不存在路径判定；
- 抖音、微信视频号在 Generic Web 前被拦截；
- 小宇宙路由、`__NEXT_DATA__`、`og:audio` 回退；
- 小宇宙调用现有 `transcribe_audio()`；
- 默认只输出 Markdown；
- opt-in JSON；
- Generic Web 正文；
- 视频时间段标题；
- Netscape Cookie 解析。

详细结果见 `TEST_REPORT.md`。

> 注意：你这次提供的 v0.4 ZIP 中没有上一版测试目录，因此无法逐文件执行“原来的 9 个测试”。本轮没有删除或重构原有微信、知乎、小红书、B站、YouTube实现，并新增了针对其关键公共行为的回归测试。

## 已知限制

- 知乎、小红书可能因登录态、反爬、页面结构调整而少抓或失败；项目目标是“快速可用”，不是保证全量。
- 小宇宙依赖公开 episode 页面中可取得的音频 URL；如果平台未来移除公开 `__NEXT_DATA__` / `og:audio` / CDN 地址，需要调整解析器。
- 抖音、视频号当前只识别来源，不维护私有签名、复杂登录、解密或专用 Sidecar。
- 本地媒体必须是实际存在的文件；不存在的“路径字符串”不会进入本地媒体通道。
- 普通网页正文抽取采用启发式，复杂交互网站可能带少量导航噪声或漏内容。
- 音视频转写和翻译仍可能有模型误差；需要精确字幕时显式输出 SRT/JSON 并复核。
