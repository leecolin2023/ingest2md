# AI agents explained: Build your first agent in 8 minutes
> **频道**: Google Cloud Tech
> **讲师**: Smitha Kolan
> **播放列表**: Modern AI Agents: From Theory to Production
> **集数**: 6/6
> **时长**: 08:29
> **语言**: English
> **字幕来源**: YouTube 自动字幕（youtube-transcript.io 匿名获取）
> **文本校对**: deepseek-v4.1-flash 局部校对（18 段有修订）
> **时间戳精度**: 段落
> **整理时间**: 2026-10-30
>
> 原文链接: https://www.youtube.com/watch?v=Zqno_vux6d8

---

## 章节

- [00:00 AI Agents Explained](https://www.youtube.com/watch?v=Zqno_vux6d8&t=0s)
- [01:05 The ReAct Framework Explained](https://www.youtube.com/watch?v=Zqno_vux6d8&t=65s)
- [02:15 The 3 Types of AI Agents (Sequential, Reactive, Planning)](https://www.youtube.com/watch?v=Zqno_vux6d8&t=135s)
- [03:30 Project Overview: The Auto-Correcting Blog Writer](https://www.youtube.com/watch?v=Zqno_vux6d8&t=210s)
- [04:15 Setting Up Google ADK & UV](https://www.youtube.com/watch?v=Zqno_vux6d8&t=255s)
- [04:50 Coding the Planner Agent](https://www.youtube.com/watch?v=Zqno_vux6d8&t=290s)
- [05:40 Adding Auto-Correction (Validation Checkers & Loop Agents)](https://www.youtube.com/watch?v=Zqno_vux6d8&t=340s)
- [06:50 Coding the Blog Writer & Root Agent](https://www.youtube.com/watch?v=Zqno_vux6d8&t=410s)

## 转写正文

### 00:00 AI Agents Explained

In this video, you're going to learn what AI agents are not just in theory, but in practice. We'll look at the ideas behind modern agents, and then we'll build your very first AI agent step by step using Google's SDK. By the end, you'll understand how agents reason, act and adapt, and you'll have code that you can actually run yourself. So what are AI agents? At the simplest level, an agent is software that doesn't just answer, it can decide and take action. Instead of generating a single response like a traditional chatbot, it looks at your request, figures out what steps need to be taken, maybe calls an API, runs code, looks at the results, and then decides what to do next. One of the clearest explanations comes from the research paper ReAct synergizing reasoning and acting in language models.

The idea in that paper was simple but powerful. Language models shouldn't just generate text in one go. They can actually reason step by step. Take an action like calling a tool or API.

### 01:05 The ReAct Framework Explained

Observe the results and then decide what to do next. That cycle of reasoning, acting, observing, and adjusting is the foundation of how modern AI agents work, and it lines up with how it's defined. Systems with reasoning, planning, and memory with enough autonomy to adapt and make decisions on behalf of the user. Now, not all agents behave the same way. A useful way to think about them is in three broad patterns. First, we have sequential agents. These run step by step like an assembly line. Step one, then step 2, then step three. They're predictable but rigid. Second, we have reactive agents. These decide in the moment. They look at the current state and ask, what should I do next. Maybe tool A one time, tool B the next. They're flexible, but they don't plan ahead. Lastly, we have deliberate or planning agents. These pause to sketch a plan then execute.

Think about booking travel. You don't just buy a flight randomly. You pick dates, hotels and then that's the order of steps that you follow through. So which of these is the right one for you. It depends on the problem. For simple, predictable flows, sequential

### 02:15 The 3 Types of AI Agents (Sequential, Reactive, Planning)

is fine. For dynamic, reactive works better. And for multi-step goals with dependencies you want planning agents. OK, that's the high level view. Now let's actually build an agent. So you can see these ideas in action. We'll build a blog writing agent. You give it a topic, it will generate a structured outline, turn that outline into a full blog post, and then suggest the alternative titles and hooks. This is where ADK's categories come in as we walk through the code, notice how the planner and writer agent are LLM agents which are powered by a model. They are wrapped in loop agents, which are workflow agents in ADK. These handle retries automatically if validation fails, and if we ever wanted something beyond that, ADK would also let us extend a custom agent by subclassing the base agent. So let's set up the environment and then go line by line through the code. First off, you need to install uv. You can do that by running the command right here. Secondly, you need to install Google ADK because we need to obviously use ADK in this.

And then let's create a file called agent in your IDE. We need to import these key libraries. And then we can start building out our very first agent.

### 03:30 Project Overview: The Auto-Correcting Blog Writer

So the first agent that we're building out is called the blog planner. Its only job is to take a topic and turn it into a structured outline. We give it the name blog planner so it's easy to identify, and we tell it which model to use, which comes from our environment file. The description is just a human readable note. The important part of the instruction is here. We actually tell it what to produce, which is a markdown outline with a title, a short introduction, four to six sections with bullet points, and a conclusion. By spelling that out, we make the output much more reliable. Finally, look at the output key. We set it to blog outline. This means whatever this agent writes will be stored in shared state under that name,

### 04:15 Setting Up Google ADK & UV

so that the next agent that can pick it up can do it automatically. Next, we add a second agent. The outline validation checker. This one doesn't write anything new. It just checks the outline. Its instruction is strict. If the outline in state has a title, an intro, four to six sections, and a conclusion, it must answer with the word OK. If something is missing, it must answer with the word retry and explain what's wrong. That way, we can automatically decide whether to accept the outline or try again. To connect the planner and the checker,

### 04:50 Coding the Planner Agent

we've wrapped them inside a loop agent called robust blog planner. The loop first runs the planner, then the checker. If the checker says OK, we're done. If the checker says retry, the loop runs the planner again with the same instructions. It can do this up to three times. This gives us a safety net. So if the model forgets something, it has another chance to get it right. Now we create another agent called blog writer. This one takes the outline we just saved in blog outline and turns it into a full markdown blog post. The instruction tells it how to write. It should assume the audience is software engineers. Skip the basics and focus on practical insights. Explain both the how and the why and include short code snippets where helpful. It should also follow the structure of the outline with proper headings.

### 05:40 Adding Auto-Correction (Validation Checkers & Loop Agents)

The finished draft is saved under blog post in shared state. Ready for the next step. Next up, we're going to add another checker, this time for the post. It's called blog post validation checker. It looks at the blog post and checks if the article has an introduction, sections that match the outline, a conclusion, and clear explanations. If it passes, the checker says OK. If not, it says retry and lists the fixes which are needed. Just like with planning, we combine the writer and its checker into a loop agent called robust blog writer. This makes the system automatically retry the writing step until the validation passes. Up to three times. Now we wrap each loop, the robust blog planner and the robust blog writer as tools. This is what lets the root agent call them directly without worrying about what's happening inside.

Finally, we put it all together with the root agent called blogger. The instructions for blogger are simple. When a user gives it a topic, first it calls the planner tool to make an outline. Then it calls the writer tool to draft the full post.

### 06:50 Coding the Blog Writer & Root Agent

And finally it adds three alternative titles and two tweet length hooks. The root agent only has access to the two tools. We exposed the planner and the writer. So its workflow is clear and controlled. You give it a topic, it plans, it writes, it checks, and then it gives you a polished blog post. You've now successfully written your first agent script. The next step is to actually run it. Head into your terminal and launch it using this command with ADK web so you can view everything inside a simple UI. Once that's running, open the local ADK web link in your browser and start interacting with the agent directly. To kick things off, I'm going to ask it to generate a blog on the top 10 use cases for AI agents. Let's see how it plans, writes, and delivers the results. Your subagents will then work together to create a blog post. And that's it.

You've built and run your first AI agent with Google's ADK. We've started from the idea of what agents are, then walked through the code step by step and finally saw it come to life in the terminal. Thank you for watching. Check out the description box for all the resources and code mentioned in this video. Check out this next video to learn how to connect your AI agent to an MCP server.
