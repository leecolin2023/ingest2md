# 为什么 Agent 时代需要一个新的 API ？ DeepSeek V4 Pro 正式版支持 Responses API 了，它和 Chat Completions API 到底有什么区别？#大模型 #vibecoding大赏  #ai新星计划  @抖音科技 @抖音小助手 #deepseek
> **来源**: 抖音
> **作者**: 王二讲Agent
> **内容获取**: Playwright 浏览器详情响应
> **ASR 后端**: sensevoice
> **已处理（秒）**: 241.667
> **转写时间**: 2026-10-23T11:19:09+00:00
> **转写模型**: sensevoice-onnx:SenseVoiceSmall
> **语言**: auto
> **时间戳精度**: chunk
>
> 原文链接: https://www.douyin.com/video/7675690881772506414

---

## 视频简介

为什么 Agent 时代需要一个新的 API ？ DeepSeek V4 Pro 正式版支持 Responses API 了，它和 Chat Completions API 到底有什么区别？#大模型 #vibecoding大赏  #ai新星计划  @抖音科技 @抖音小助手 #deepseek

## 整理正文

### 00:00–04:01

如果你调用过 DeepSeek 的 API，你一定用过 Chat Completions 协议：发一个 messages 数组，拿回一段文本，简单粗暴。但聪明的你应该已经注意到了，Codex 已经不用 Chat Completions 协议了，就连 DeepSeek V4 Pro 和 Flash 也原生支持 Responses API 协议了。

为什么要换协议呢？我翻了 Codex 的架构博客、DeepSeek 的 API 文档，可以自信地、大方地、光明磊落地帮你搞清楚三件事：Responses API 到底改变了什么？为什么 Agent 时代需要一个新的 API？DeepSeek V4 Pro 支持它意味着什么？

Hello，大家好，我是二哥。今天用三分钟给你讲清楚 Responses API 和 Chat Completions API 到底有什么区别。系好安全带，我们速速出发。

先说第一个区别：**输入输出的格式变了。** Chat Completions 协议里，所有的东西都是 message。你输入的是 user message，模型回复的是 assistant message，工具返回的是 tool message。不管什么类型的内容，都塞在同一种 messages 数组里，靠 role 字段区分。

Responses API 不一样，它把每种输出拆成了独立的类型：文本回复是 message，推理过程是 reasoning，工具调用是 function_call，生成图片是 image_generation_call，各管各的，互不干扰。

打个比方，Chat Completions 像是在一个群聊里，不管你是汇报工作、发通知还是分享文件，都只能打字发消息；Responses API 像飞书工作台，文档、审批、日程、视频会议，每种操作都有自己的入口。

那聪明的你肯定想到了，光改个格式，就值得专门出一套新 API 吗？当然不止这些，还有更关键的**状态管理和内置工具**。

Chat Completions 是无状态的，每次调用都要把完整的聊天记录、messages 数组重新发一遍。第一轮聊天之后，后续请求需要把之前的内容重发。Responses API 给了一个新的选项：previous_response_id。你只需要告诉服务端上一轮的响应 ID 是什么，服务端就通过 ID 去自己记录的上下文里找，不用你重发。一边是每轮都把完整记录重发，一边是指定一个 ID，这就是无状态和服务端状态管理的区别。

再看内置工具。Chat Completions 只支持你自己定义的函数，联网搜索、代码执行都得自己接第三方服务。Responses API 直接内置了联网搜索、代码执行、文件检索。你只需要写一行 tools，type 为 web_search，剩下的 API 帮你搞定。

一句话总结这个区别：Chat Completions 是为聊天时代设计的，Responses API 是为 Agent 设计的。

那聪明的你肯定又要问了，DeepSeek V4 Pro 支持 Responses API 有什么实际意义？

最直接的好处，你可以把 DeepSeek V4 Pro 直接接入 Codex 里用，因为 Codex 用的就是 Responses API，兼容性会更好。以前你想在 Codex 里用国产模型，中间得加一层代理进行格式转换；现在原生支持了，改一下 base URL 就能直接用，不用再做任何适配。

更重要的是，Responses API 不再是 OpenAI 的专属格式。DeepSeek V4 正式版支持了，其他模型厂商迟早也会跟上。它正在成为 Agent 时代的行业标准，就像当年 Chat Completions 的 messages 格式成为聊天 API 的行业标准一样。

最后简单总结：Chat Completions 为聊天而生，Responses API 为 Agent 而生。核心区别有三个：类型化输出、服务端状态管理、内置工具。如果你在做 Agent 开发，建议现在就切到 Responses API。

这个知识点你学会了吗？想解锁更多 AI 硬核知识，点赞关注。我是二哥，咱们下期见。
