# output 最新增量内容处理清单（2026-10-26）

本清单记录两次素材提交的处理进度，按 2026-10-26 最新用户要求：所有原先未处理稿件均生成 Deep Read + Learning，不再以视频是否超过十分钟决定处理方法。原始时长分类仅供追踪：

- [ec142013](https://github.com/leecolin2023/ingest2md/commit/ec142013f68295a04ddcd62fe0912205e941d21a)：新增 77 份本地视频转写，每份输出含 `content.md` 和 `transcript.txt`。
- [fb7579d6](https://github.com/leecolin2023/ingest2md/commit/fb7579d6c5bff0df1dc898291d7a6662a7d25379)：新增 7 份 RAG/BM25 抖音转写。

**原始时长：**保持历史统计的 600 秒分类以便溯源；当轮新指令已覆盖原有时长分流逻辑：原有未处理稿件一律生成双稿。

**目录：** `output-Learning/`（长视频两份 Markdown）；`output-Refinement/`（短视频一份 Markdown），沿用仓库大小写约定。原始 `output/` 保留不改。

**进度（本轮中间检查）：**总数 **84 篇**；此前 7 篇已 Refine、3 篇已有双稿；本轮新增 **42 篇双稿（84 份 Markdown）**。目前共有 **45 篇双稿**、**7 篇仅 Refine**，尚待本次双稿处理 **32 篇**。已提交指文件写入 GitHub，不代表人工核听或完整独立 D/R→L 执行验收。

> Learning V0.7.0 要求 Deep Read、Review 以同一原稿分别独立运行并有执行记录；本轮已生成的 Learning 内容含该限制声明。后续若要求严格遵守完整运行时隔离，必须另有具备隔离调用和留痕能力的宿主。

## A. 超过 10 分钟：Deep Read + Learning（37 篇）

| 输入路径 | 时长 m:ss | 时长秒 | 处理状态 |
| --- | ---: | ---: | --- |
| `output/20261025__01 第一次直播答疑回放/content.md` | 36:45 | 2205.31 | 待处理 |
| `output/20261025__02 直播梳理LLM原理01/content.md` | 26:33 | 1593.73 | 待处理 |
| `output/20261025__03 直播-LLM原理02/content.md` | 39:51 | 2391.60 | 待处理 |
| `output/20261025__04 客户系统的Rag到底怎么建？_ev/content.md` | 10:37 | 637.42 | Deep Read + Learning 已提交（Review 调用隔离未验证） |
| `output/20261025__04 直播-LLM原理-03/content.md` | 11:48 | 708.80 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__05 重学langchain01/content.md` | 36:11 | 2171.80 | 待处理 |
| `output/20261025__06 用postgre + pgvector实现稠密稀疏向量_ev/content.md` | 10:34 | 634.77 | Deep Read + Learning 已提交（Review 调用隔离未验证） |
| `output/20261025__06 重学langchain02/content.md` | 39:27 | 2367.80 | 待处理 |
| `output/20261025__07 1.19看看行情/content.md` | 32:45 | 1965.07 | 待处理 |
| `output/20261025__08 1.19看看行情/content.md` | 29:12 | 1752.73 | 待处理 |
| `output/20261025__09 1.27回放 什么是Skills/content.md` | 22:04 | 1324.87 | 待处理 |
| `output/20261025__2.25 武汉18k 教授/content.md` | 39:18 | 2358.54 | 待处理 |
| `output/20261025__2.25 武汉25k 电商头部 - Trim/content.md` | 40:27 | 2427.51 | 待处理 |
| `output/20261025__2.26 武汉边缘面试官18k/content.md` | 23:37 | 1417.90 | 待处理 |
| `output/20261025__2.26 深信服18k （重点看）/content.md` | 70:05 | 4205.30 | 待处理 |
| `output/20261025__3.16 深圳30k 两轮已经过了/content.md` | 83:18 | 4998.85 | 待处理 |
| `output/20261025__3.9 创业无限画布深圳30k(重点看)-裁切/content.md` | 51:09 | 3069.82 | 待处理 |
| `output/20261025__3.9 字节外包-裁切/content.md` | 44:42 | 2682.92 | 待处理 |
| `output/20261025__3.9 重庆50k-裁切/content.md` | 32:47 | 1967.94 | 待处理 |
| `output/20261025__32 自媒体运营Agent 5_ev/content.md` | 12:03 | 723.66 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__4.22 上海35K实战面试-1面裁切/content.md` | 56:42 | 3402.33 | 待处理 |
| `output/20261025__4.23 上海35K实战面试-2面裁切/content.md` | 51:53 | 3113.62 | 待处理 |
| `output/20261025__7.17 30k杭州阿里技术支持/content.md` | 14:01 | 841.93 | 待处理 |
| `output/20261025__7.20 西安35k Ai agent/content.md` | 18:06 | 1086.06 | 待处理 |
| `output/20261026__10 2.9 面试辅导01/content.md` | 36:41 | 2201.13 | 待处理 |
| `output/20261026__11 2.9 面试辅导02/content.md` | 38:26 | 2306.53 | 待处理 |
| `output/20261026__12 2.9面试辅导03/content.md` | 22:54 | 1374.73 | 待处理 |
| `output/20261026__13 3.2 评测集解析/content.md` | 38:30 | 2310.53 | Deep Read + Learning 已提交（Review 调用隔离未验证） |
| `output/20261026__14 3.2 面试题解读/content.md` | 30:16 | 1816.33 | 待处理 |
| `output/20261026__15 3.4 如何用Ai写自己定制化业务的简历01/content.md` | 37:20 | 2240.07 | 待处理 |
| `output/20261026__17 3.8 字节面试题赏析/content.md` | 39:02 | 2342.40 | 待处理 |
| `output/20261026__19 3.16 鸭哥26k真题解析 01/content.md` | 39:51 | 2391.60 | 待处理 |
| `output/20261026__20 3.16 鸭哥26k真题解析 02/content.md` | 22:23 | 1343.27 | 待处理 |
| `output/20261026__21 2期新同学与面试题解读/content.md` | 34:36 | 2076.53 | 待处理 |
| `output/20261026__22 Agent集群第二课/content.md` | 39:19 | 2359.60 | 待处理 |
| `output/20261026__23 3.30 简历辅导/content.md` | 37:45 | 2265.47 | 待处理 |
| `output/20261026__24 4.1 企业真题解析1/content.md` | 39:28 | 2368.07 | 待处理 |

## B. 不超过 10 分钟：Refine（47 篇）

| 输入路径 | 时长 m:ss | 时长秒 | 处理状态 |
| --- | ---: | ---: | --- |
| `output/20261025__01 面试最重要的就是吹_ev/content.md` | 7:05 | 425.37 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__03 如何向面试官介绍我们的8个项目_ev/content.md` | 9:35 | 575.11 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__05 用户的查询流程解析_ev/content.md` | 3:39 | 219.53 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__07 Topk N Rerank_ev/content.md` | 8:37 | 517.48 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__08 为啥项目一定要Rerank_ev/content.md` | 4:02 | 242.10 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__09 需不需要降维和量化_ev/content.md` | 6:58 | 418.86 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__10 知识库的数据频繁变动怎么办？_ev/content.md` | 3:25 | 205.98 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__11 客服遇到高并发怎么办？_ev/content.md` | 8:44 | 524.22 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__12 如何提升召回率？_ev/content.md` | 2:32 | 152.36 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__13 如何统计召回率和准确率_ev/content.md` | 8:01 | 481.83 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__14 客服系统如何返回多模态的数据？_ev/content.md` | 1:45 | 105.17 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__15 LLM性能优化 01_ev/content.md` | 8:12 | 492.19 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__16 LLM性能优化 02_ev/content.md` | 8:10 | 490.33 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__17 RTC语音链路优化_ev/content.md` | 7:08 | 428.33 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__18 评测集1_ev/content.md` | 2:43 | 163.33 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__19 评测集2_ev/content.md` | 8:36 | 516.52 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__20 评测集3_ev/content.md` | 8:51 | 531.92 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__21 评测集4_ev/content.md` | 8:48 | 528.91 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__22 数据中台1_ev/content.md` | 5:34 | 334.51 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__23 数据中台2_ev/content.md` | 3:53 | 233.67 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__24 数据中台3_ev/content.md` | 6:20 | 380.65 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__25 数据中台4_ev/content.md` | 3:52 | 232.07 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__27 直播切片项目2_ev/content.md` | 5:20 | 320.42 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__28 自媒体运营Agengt1_ev/content.md` | 8:42 | 522.05 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__29 自媒体运营Agengt2_ev/content.md` | 6:13 | 373.53 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__30 自媒体运营Agent 3_ev/content.md` | 7:15 | 435.55 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__31 自媒体运营Agent 4_ev/content.md` | 4:58 | 298.56 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__33 MCP集群1_ev/content.md` | 5:08 | 308.28 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__34 MCP集群2_ev/content.md` | 2:14 | 134.35 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__35 Mcp集群3_ev/content.md` | 4:42 | 282.16 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__36 MCP集群4_ev/content.md` | 4:31 | 271.25 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__37 Ai素材管理中心_ev/content.md` | 4:54 | 294.95 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__38 销售考核系统1_ev/content.md` | 3:13 | 193.48 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__39 销售考核系统2_ev/content.md` | 9:45 | 585.25 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__40 模型微调1_ev/content.md` | 3:06 | 186.08 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__41 模型微调2_ev/content.md` | 6:33 | 393.76 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__42 模型微调3_ev/content.md` | 2:39 | 159.38 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__43 模型微调4_ev/content.md` | 7:11 | 431.70 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261025__44 模型微调5_ev/content.md` | 9:58 | 598.98 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261026__16 3.4 如何用Ai写定制化的业务简历 02/content.md` | 7:30 | 450.47 | Deep Read + Learning 已提交（Review 隔离未验证） |
| `output/20261024__面试官问你Rag如何保证100_准确，千万注意这就是陷阱！ #ai #ai应用开发 #大模型开发 #懂王ai.md` | 4:06 | 246.18 | Refine 已提交 |
| `output/20261025__RAG检索阶段，BM25和向量检索为什么互补？#rag #ai大模型 #人工智能 #计算机.md` | 5:21 | 321.69 | Refine 已提交 |
| `output/20261025__【快问快答】字节 RAG 面经夺命十连问 #AI大模型 #大模型面试 #RAG #Agent #程序员.md` | 6:25 | 385.47 | Refine 已提交 |
| `output/20261025__为什么搜索、RAG、Agent 至今离不开 BM25？三个直觉一次讲透 #BM25 #RAG #向量检索 #AIAgent #大模型.md` | 3:04 | 184.48 | Refine 已提交 |
| `output/20261025__搞不懂BM25，你的RAG检索可能白做了！ #我在抖音学ai #rag知识库 #ai #混合检索 #向量检索.md` | 4:05 | 245.50 | Refine 已提交 |
| `output/20261025__混合检索中，BM25 和向量检索到底怎么配合？ #rag #aiagent#openai #人工智能 #知识库.md` | 7:23 | 443.15 | Refine 已提交 |
| `output/20261025__面试必考题BM25+向量检索为啥要混合检索？召回条数怎么配？ #大模型面试 #RAG #人工智能 #大模型 #ai.md` | 4:49 | 289.37 | Refine 已提交 |

---

此清单是实际执行状态记录，不是所有素材已完成的声明。