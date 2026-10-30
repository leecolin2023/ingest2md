# Plan 模式已经淘汰了吗？ Claude Code 团队的 Boris Cherny 说：“plan mode was useful, and is no longer useful.” 翻译翻译就是 Plan 模式以前有用，现在没用了。#抖音前沿科技首发计划  #AI新星计划 #Anthropic #大模型 #王二讲Agent
> **来源**: 抖音
> **作者**: 王二讲Agent
> **内容获取**: Playwright 浏览器详情响应
> **ASR 后端**: sensevoice
> **已处理（秒）**: 261.973
> **转写时间**: 2026-10-26T11:10:45+00:00
> **转写模型**: sensevoice-onnx:SenseVoiceSmall
> **语言**: auto
> **时间戳精度**: chunk
>
> 原文链接: https://www.douyin.com/video/7690807740213529882

---

## 视频简介

Plan 模式已经淘汰了吗？ Claude Code 团队的 Boris Cherny 说：“plan mode was useful, and is no longer useful.” 翻译翻译就是 Plan 模式以前有用，现在没用了。#抖音前沿科技首发计划  #AI新星计划 #Anthropic #大模型 #王二讲Agent

## 转写正文

### 00:00–04:21

2026年9月24日，阿门娜发了一篇文章，标题相当暴论plan mode is dead。作者正在做一款AI编程产品newance之前是GitHub的高级工程师文章第二天被转发到Hacker News截止到发稿前共有508条评论，真正让讨论炸锅的是评论区里的一条回复。 code团队的risney留言说，plan mode was useful and is no longer useful。翻译翻译就是plan模式以前有用，现在没用了。要知道，就在今年1月31日，他还建议大家每个复杂任务都从plan模式开始。

精力花在计划上，让 Claude 一次就把代码写对，8个月态度可以说大反转，这也是AI时代的最大问题。明明不到一年时间一切都变了，并且变得让你摸不着头脑。为什么Claude Code 开发者plan模式的倡导者，说plan模式没用了。我翻了那篇原文Claude Code 和 Codex的官方文档可以自信的大方的光明磊落的帮你搞清楚这三件事，Claude Code 的 plan 模式底层到底做了什么？为什么说他死了，以后还要不要先规划再动手。hello,大家好，我是二哥呀，今天用3分钟。

帮你把plan模式讲清楚，先说第一件事，plan模式底层到底做了什么？在Claude Code 里按Shift+Tab或者输入/plan就进入了plan模式。官方文档的说法是plan只做研究，提出方案，等你批准之后才修改代码。那聪明的你肯定要问Claude Code 本身注册了很多工具。为什么plan模式能只做计划不动手呢？答案很简单，plan做的事情只是在每条用户消息后面追加了一句提醒，You are in plan mode. Please don't code yet.换句话说，plan模式做的是让agent别着急写代码，别动工具。

及否则容易让prompt cache失效。之前讲prefix caching就讲过工具定义要放在请求的最前面，并且要尽量保持不动，否则后面的缓存会全部作废。Codex的思路类似，它的plan模式是一套协作模板，要求模型不能执行任何修改。有疑问就调用request user input来问你，最后交出一份decomp计划。派ag做得更激进，根本就没有内置plan模式只能扩展。当你打开plan模式派agent会通过sactive tools把edit和 write这两个工具直接拿掉bash也只放行，只读命令。那聪明的。

肯定想到了plan为什么会被判死刑。ned在文章里说，plan模式原本有两项职责。第一，给agent足够精确的指令。第二，帮用户理解自己要做的到底是什么。第一项正在快速废弃。因为模型越来越聪明，能读懂大型的代码库了，模型能自己做出可靠的决定越多，需要用户提前写进计划里的就越少。churney的说法更直接，用上Opus 5.5之后，他觉得模型基本能猜对意图。因为Opus 5.5对多轮交互的意图理解有了大幅提升，早期模型一听到任务就急着写代码的毛病，已经被治好。

newance透露说，他曾经习惯把计划做成一份独立的spec文档，还专门加一个能让自己浏览 spec的功能。结果发现spec信息更多了，却没有更清楚。所以他的结论是，我们把规划这个动作和计划这份文档混为一谈了。我们需要的是planning，但不需要plan mode了。以前是计划、审批、执行三步走。现在像Codex这样的agent是理解、动手、检查、澄清、调整，再动手，规划和执行交织在同一个 loop 里，两者的边界正在消失。换句话说，模型越来越聪明，根本不需要我们。

主动让他开启plan模式，审批后，再让他开始。Agent 会在需要的时候自己做好计划，然后再动手，并且计划完全不需要我们人去审批。那聪明的你肯定又要问了。那我以后还要不要先规划再动手？看情况，当需求本身不清楚的时候，模型仍然会搞错。一旦搞错，在复杂系统里不仅会浪费大量上下文与 token，重构的成本也很高。plan模式真正的价值，是让用户停下来看一眼turnurney就坦诚plan模式不会被删掉，plan会一直存在，只是Shift+Tab这个快捷键可能会分给别的功能。

Claude Code 官方的最佳实践里也给了一条很实用的建议，方向不确定、要改多个文件、对代码不熟悉，这三种情况先规划。如果一句话就能说清楚要改什么，就跳过计划。by的作者marner认为，把计划落盘，能让agent跨会话共享，还能和代码一起做版本管理。所以对我们开发者来说，一句话说得清，直接让agent动手。方向拿不准，先用/plan看一眼方案，要跨会话，或者要分给多个agent去做，就让 Claude 用 AskUserQuestion把需求问清楚，写成SPEC.md再开一个新会话去。

执行，这也是Claude Code官方推荐的做法。我个人也觉得plan模式暂时还死不了，因为模型还不足够强，等模型足够强了，确实就不需要plan模式了。从我自己的使用情况来看，plan模式用的越来越少，真正的架构演进往往是一边讨论，一边调整，而非单次的生成计划执行计划。这个知识点你学会了吗？想解锁更多agent硬核知识，点赞关注我是二哥，咱们下期见。
