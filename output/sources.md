# 转写链接记录

撰写素材的转写索引。本文件由 `ingest2md` 自动维护：每次成功生成产物后会新增或刷新一行，表格以外的手写内容不会被改动。

| 链接 | Extractor | 产物路径 | 日期 |
|---|---|---|---|
| https://www.douyin.com/video/7694555091273010495 | DouyinExtractor | `怎么设计Agent的Human-in-the-loop 三分钟带你搞懂，在 Agent 的执行过程中，如何设置一些需要人来做决定的节点，比如批准、修改或者拒绝，__7694555091273010495.md` | 2026-10-16 |

## 产物命名规则（实测确认，v0.10.2）

- 命名：`<标题>__<来源ID>`，标题净化非法字符、最长 80 字符；无来源 ID 时只有标题。
- **默认（formats: ["md"]）且无本地图片/附件时是单个 .md 文件**；
- 存在本地图片、附件或额外格式（txt / srt / json）时才会建同名文件夹，里面放 `<标题>.md` 和 `transcript.txt` / `document.json` / `transcript.srt`。
- 抖音实测命名：`<视频描述（截断至 80 字符）>__<aweme_id>.md`。
- 表格中的"产物路径"相对于本文件所在的 `output/` 目录。

## 备注

- 2026-10-16：本机网络在无 Cookie 时会被抖音下发滑块验证（`verify.zijieapi.com`），详情接口被拦截并抓到占位视频；配置 `.config/douyin-cookies.txt` 后重跑成功（内容获取=Playwright 浏览器详情响应，作者=王二讲Agent，音频时长 270.6s，ASR=本地 SenseVoice，规范化=DeepSeek V4.1 Flash）。
