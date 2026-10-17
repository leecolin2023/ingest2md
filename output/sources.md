# 转写链接记录

撰写素材的转写索引。本文件由 `ingest2md` 自动维护：每次成功生成产物后会新增或刷新一行，表格以外的手写内容不会被改动。

| 链接 | Extractor | 产物路径 | 日期 |
|---|---|---|---|
| https://www.douyin.com/video/7694555091273010495 | DouyinExtractor | `怎么设计Agent的Human-in-the-loop 三分钟带你搞懂，在 Agent 的执行过程中，如何设置一些需要人来做决定的节点，比如批准、修改或者拒绝，__7694555091273010495.md` | 2026-10-16 |
| https://www.douyin.com/video/7691701133199689467 | DouyinExtractor | `Agent 意图识别怎么做？面试必会的 4 种方案_#人工智能 #AIAgent #意图识别 #FunctionCalling #RAG__7691701133199689467.md` | 2026-10-16 |
| https://www.douyin.com/video/7667408575207148863 | DouyinExtractor | `王自如聊AI意图识别 想要提高AI在模糊输入和意图识别指令方面的准确性，一是可以先调用轻量级模型API来梳理用户意图，二是将用户需求重写，放大信号提高准确性，然__7667408575207148863.md` | 2026-10-17 |
| https://www.douyin.com/video/7694582320585559322 | DouyinExtractor | `字节AI面试：Agent意图路由怎么设计？ #人工智能 #AI #AI新星计划 #程序员 #Agent__7694582320585559322.md` | 2026-10-16 |
| https://www.douyin.com/video/7687905443414396200 | DouyinExtractor | `面试官只要敢问你意图识别，按我这么说，20k到手！ #ai #ai应用开发 #大模型开发 #懂王ai__7687905443414396200.md` | 2026-10-16 |
| https://www.douyin.com/video/7694525797121527094 | DouyinExtractor | `什么是Jev意图识别？ #ai #ai应用开发 #大模型开发 #懂王ai__7694525797121527094.md` | 2026-10-16 |
| https://www.douyin.com/video/7682777314991672617 | DouyinExtractor | `面AI Agent通关，Java老底子帮了我大忙 Agent 流程、调优全部聊透，结尾突出来三道 Java 八股。感慨：不会八股的程序员不是好程序员，有 Jav__7682777314991672617.md` | 2026-10-16 |
| https://www.douyin.com/video/7683871840766414090 | DouyinExtractor | `金融Agent面试有感_;之前项目烂尾,现在重新探索和规 金融自研 AI Agent 岗位，上一个候选人把项目做烂。面试重点考察 Agent 设计、文档、记忆存__7683871840766414090.md` | 2026-10-16 |
| https://www.douyin.com/video/7685323277253791028 | DouyinExtractor | `大厂面试压迫感！小米Java Agent岗，连环拷问..., 小米自研后端 Java 面试，意向 Agent 开发。典型大厂风格，盯住一个场景持续深挖，覆盖分库__7685323277253791028.md` | 2026-10-16 |
| https://www.douyin.com/video/7686434835233115398 | DouyinExtractor | `小米自研Java面经｜Agent岗位面试,场景连环追问(2) 小米后端面试实录，投递 Agent 开发方向。大厂面试压迫感十足，单一场景持续追问，Agent 岗__7686434835233115398.md` | 2026-10-16 |
| https://www.douyin.com/video/7687944720114322742 | DouyinExtractor | `拿到50W+ Agent 开发 offer，一面上篇复盘 北京大厂 Agent 开发岗，一面上篇！围绕 Agent 业务 + Java 工程化深挖，全程硬核拷问__7687944720114322742.md` | 2026-10-16 |
| https://www.douyin.com/video/7689869201732816162 | DouyinExtractor | `万联易达 Agent 一面｜项目深挖，全是落地踩坑问题 北京万联易达集团 Agent 岗位一面复盘。面试官深挖流式输出滑动窗口检测、卡片组件、ReAct 执行链__7689869201732816162.md` | 2026-10-16 |
| https://www.douyin.com/video/7696811818690777770 | DouyinExtractor | `孕35周 听了姐妹们的建议准爸爸重新整理了待产包 一定要让他收拾噢 这样就能记住所有东西 住院时好找到#待产包 #准爸爸 #孕晚期 #卸货倒计时__7696811818690777770.md` | 2026-10-17 |

## 产物命名规则（实测确认，v0.10.2）

- 命名：`<标题>__<来源ID>`，标题净化非法字符、最长 80 字符；无来源 ID 时只有标题。
- **默认（formats: ["md"]）且无本地图片/附件时是单个 .md 文件**；
- 存在本地图片、附件或额外格式（txt / srt / json）时才会建同名文件夹，里面放 `<标题>.md` 和 `transcript.txt` / `document.json` / `transcript.srt`。
- 抖音实测命名：`<视频描述（截断至 80 字符）>__<aweme_id>.md`。
- 表格中的"产物路径"相对于本文件所在的 `output/` 目录。

## 备注

- 2026-10-16：本机网络在无 Cookie 时会被抖音下发滑块验证（`verify.zijieapi.com`），详情接口被拦截并抓到占位视频；配置 `.config/douyin-cookies.txt` 后重跑成功（内容获取=Playwright 浏览器详情响应，作者=王二讲Agent，音频时长 270.6s，ASR=本地 SenseVoice，规范化=DeepSeek V4.1 Flash）。
