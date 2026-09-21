"""Zhihu question extractor: one question + as many loaded answers as possible -> one Markdown.

This intentionally favors fast, readable corpus creation over archival accuracy.
It uses the rendered question page rather than depending on Zhihu's signed API.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ingest2md.browser import browser_context, load_netscape_cookies
from ingest2md.config import Settings, load_settings
from ingest2md.htmlutils import clean_fragment
from ingest2md.model import Document
from ingest2md.netutils import DEFAULT_USER_AGENT
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)

_HOSTS = {"zhihu.com", "www.zhihu.com"}
_QUESTION_RE = re.compile(r"/question/(\d+)(?:/answer/(\d+))?")
_ANSWER_RE = re.compile(r"/question/(\d+)/answer/(\d+)")

@dataclass
class ZhihuAnswer:
    answer_id: str
    author: str
    body_md: str
    url: str
    time_text: str = ""
    vote_text: str = ""


@dataclass
class ZhihuQuestionSnapshot:
    question_id: str
    title: str
    detail_md: str
    expected_answers: int | None
    answers: list[ZhihuAnswer]


class ZhihuExtractor:
    name = "知乎问题"
    description = "zhihu.com/question/... → 问题 + 尽可能多回答 → 单个 Markdown"

    def __init__(self, settings: Settings | None = None, runtime=None):
        self.settings = settings
        self.runtime = runtime

    def match(self, url: str) -> bool:
        return host_of(url) in _HOSTS and bool(_QUESTION_RE.search(urlparse(url).path))

    async def extract(self, url: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        match = _QUESTION_RE.search(urlparse(url).path)
        if not match:
            raise ValueError("不是知乎问题/回答链接")
        qid = match.group(1)
        canonical = f"https://www.zhihu.com/question/{qid}"
        answers: dict[str, ZhihuAnswer] = {}
        question: ZhihuQuestionSnapshot | None = None

        async with browser_context(
            self.runtime.browser if self.runtime else None,
            user_agent=DEFAULT_USER_AGENT,
            locale="zh-CN",
        ) as context:
            cookie_file = settings.zhihu_cookies_file or settings.cookies_file
            if cookie_file:
                cookies = load_netscape_cookies(cookie_file, "zhihu.com")
                if cookies:
                    await context.add_cookies(cookies)
            page = await context.new_page()
            try:
                response = await page.goto(canonical, wait_until="domcontentloaded", timeout=35_000)
            except Exception as exc:
                message = str(exc)
                if "ERR_BLOCKED_BY_ADMINISTRATOR" in message:
                    raise RuntimeError("当前运行环境阻止访问知乎（ERR_BLOCKED_BY_ADMINISTRATOR）") from exc
                raise RuntimeError(f"知乎页面访问失败: {message}") from exc
            if response and response.status >= 400:
                raise RuntimeError(f"知乎页面访问失败: HTTP {response.status}")
            await page.wait_for_timeout(1500)

            stable_rounds = 0
            previous_count = -1
            for _ in range(60):
                await _expand_visible(page)
                html = await page.content()
                snapshot = parse_question_page(html, canonical, qid)
                question = _prefer_question(question, snapshot)
                for answer in snapshot.answers:
                    answers.setdefault(answer.answer_id, answer)
                if settings.max_answers and len(answers) >= settings.max_answers:
                    break
                if len(answers) == previous_count:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                    previous_count = len(answers)
                expected = snapshot.expected_answers
                if expected is not None and len(answers) >= expected:
                    break
                if stable_rounds >= 5:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(900)

        if not question or not question.title:
            raise RuntimeError("未能读取知乎问题标题；可能需要登录 Cookie 或页面结构已变化")
        ordered = list(answers.values())
        if settings.max_answers:
            ordered = ordered[: settings.max_answers]
        if not ordered:
            raise RuntimeError("未抓到知乎回答；可尝试提供已登录知乎的 Netscape Cookie")

        body = render_question_markdown(question, ordered)
        count_text = str(len(ordered))
        if question.expected_answers is not None:
            count_text += f" / 页面显示 {question.expected_answers}"
        metadata = [("来源", "知乎"), ("获取回答", count_text)]
        return Document(
            title=question.title,
            source_url=canonical,
            source_id=qid,
            source_type="zhihu_question",
            metadata=metadata,
            body_md=body,
        )


async def _expand_visible(page) -> None:
    # Zhihu commonly collapses long answers behind “阅读全文”. Ignore click failures.
    try:
        await page.evaluate("""
        () => {
          for (const el of document.querySelectorAll('button, a')) {
            const t = (el.textContent || '').trim();
            if (t === '阅读全文' || t === '展开阅读全文') {
              try { el.click(); } catch (_) {}
            }
          }
        }
        """)
        await page.wait_for_timeout(150)
    except Exception:
        pass


def _prefer_question(old: ZhihuQuestionSnapshot | None,
                     new: ZhihuQuestionSnapshot) -> ZhihuQuestionSnapshot:
    if old is None:
        return new
    if not old.detail_md and new.detail_md:
        old.detail_md = new.detail_md
    if old.expected_answers is None and new.expected_answers is not None:
        old.expected_answers = new.expected_answers
    if not old.title and new.title:
        old.title = new.title
    return old


def _answer_id(item, qid: str, body_md: str) -> str:
    for link in item.select('a[href*="/answer/"]'):
        m = _ANSWER_RE.search(link.get("href", ""))
        if m and m.group(1) == qid:
            return m.group(2)
    # Fallback: stable-enough local dedupe for rendered answers lacking canonical links.
    return "dom-" + hashlib.sha1(body_md.encode("utf-8")).hexdigest()[:16]


def parse_question_page(html: str, url: str, qid: str) -> ZhihuQuestionSnapshot:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1.QuestionHeader-title, .QuestionHeader-title")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    if not title and soup.title:
        title = re.sub(r"\s*[-–]\s*知乎\s*$", "", soup.title.get_text(" ", strip=True))

    detail = ""
    detail_node = soup.select_one(
        ".QuestionRichText .RichContent-inner, .QuestionHeader-detail .RichContent-inner, "
        ".QuestionHeader-detail"
    )
    if detail_node:
        detail = clean_fragment(str(detail_node))

    expected = None
    for node in soup.select(".List-headerText, .QuestionHeader-answers, .QuestionHeader-content"):
        text = node.get_text(" ", strip=True)
        m = re.search(r"([\d,]+)\s*个回答", text)
        if m:
            expected = int(m.group(1).replace(",", ""))
            break

    answers: list[ZhihuAnswer] = []
    seen = set()
    selectors = ".List-item, .ContentItem.AnswerItem, .AnswerItem"
    for item in soup.select(selectors):
        content = item.select_one(
            ".RichContent-inner, .CopyrightRichText-richText, .RichContent"
        )
        if not content:
            continue
        body_md = clean_fragment(str(content))
        if len(body_md) < 20:
            continue
        aid = _answer_id(item, qid, body_md)
        if aid in seen:
            continue
        seen.add(aid)
        author_node = item.select_one(".AuthorInfo-name, .UserLink-link, .AuthorInfo-head")
        author = author_node.get_text(" ", strip=True) if author_node else "匿名/未知"
        time_node = item.select_one(".ContentItem-time, [data-tooltip*='发布']")
        vote_node = item.select_one("button.VoteButton--up, .VoteButton--up")
        answer_url = f"https://www.zhihu.com/question/{qid}/answer/{aid}" if aid.isdigit() else url
        answers.append(ZhihuAnswer(
            answer_id=aid,
            author=author,
            body_md=body_md,
            url=answer_url,
            time_text=time_node.get_text(" ", strip=True) if time_node else "",
            vote_text=vote_node.get_text(" ", strip=True) if vote_node else "",
        ))
    return ZhihuQuestionSnapshot(qid, title, detail, expected, answers)


def render_question_markdown(question: ZhihuQuestionSnapshot,
                             answers: list[ZhihuAnswer]) -> str:
    parts: list[str] = []
    if question.detail_md:
        parts.extend(["## 问题描述", "", question.detail_md, ""])
    parts.extend(["## 回答", ""])
    for index, answer in enumerate(answers, 1):
        parts.append(f"### 回答 {index}｜{answer.author}")
        meta = []
        if answer.time_text:
            meta.append(answer.time_text)
        if answer.vote_text:
            meta.append(answer.vote_text)
        if answer.url:
            meta.append(f"原回答：{answer.url}")
        if meta:
            parts.append("> " + " · ".join(meta))
        parts.extend(["", answer.body_md, "", "---", ""])
    return "\n".join(parts).rstrip("-\n ") + "\n"
