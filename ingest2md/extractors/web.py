"""Generic web article extractor.

The goal is deliberately lightweight: extract the most article-like area and
produce one readable Markdown file. It is not a forensic HTML snapshotter.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ingest2md.browser import browser_context
from ingest2md.htmlutils import clean_fragment, meta_content
from ingest2md.netutils import DEFAULT_USER_AGENT
from ingest2md.model import Document
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)


class GenericWebExtractor:
    name = "普通网页"
    description = "普通 http/https 网页 → Trafilatura 主正文 Markdown"
    acquisition_plan = (
        "HTTP 获取页面",
        "Trafilatura 提取主正文",
        "正文不足时使用现有浏览器渲染后再次提取",
    )

    def match(self, url: str) -> bool:
        return url.startswith(("http://", "https://")) and bool(host_of(url))

    async def extract(self, url: str, output_dir: Path) -> Document:
        try:
            html = await _fetch_http(url)
            doc = parse_web_page(html, url)
            if len(doc.body_md) >= 120:
                return doc
        except Exception as exc:
            logger.info("普通 HTTP 抓取未取得足够正文，尝试浏览器渲染: %s", exc)
        runtime = getattr(self, "runtime", None)
        html, final_url = await _fetch_browser(
            url,
            browser_runtime=runtime.browser if runtime is not None else None,
        )
        return parse_web_page(html, final_url)


async def _fetch_http(url: str) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        follow_redirects=True,
        timeout=20,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def _fetch_browser(url: str, browser_runtime=None) -> tuple[str, str]:
    async with browser_context(
        browser_runtime,
        user_agent=DEFAULT_USER_AGENT,
        locale="zh-CN",
    ) as context:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(1200)
        return await page.content(), page.url


def _best_content_node(soup: BeautifulSoup):
    selectors = [
        "article", "main article", "[role=main] article", ".article-content",
        ".article-body", ".post-content", ".entry-content", ".markdown-body",
        "main", "[role=main]", ".content",
    ]
    candidates = []
    for selector in selectors:
        for node in soup.select(selector):
            text_len = len(" ".join(node.stripped_strings))
            if text_len:
                candidates.append((text_len, node))
    if candidates:
        return max(candidates, key=lambda x: x[0])[1]
    return soup.body or soup


def parse_web_page(html: str, url: str) -> Document:
    soup = BeautifulSoup(html, "html.parser")
    title = (
        meta_content(soup, prop="og:title") or meta_content(soup, name="twitter:title")
        or (soup.title.get_text(" ", strip=True) if soup.title else "")
        or host_of(url)
        or "网页"
    )
    author = meta_content(soup, name="author") or meta_content(soup, prop="article:author")
    published = meta_content(soup, prop="article:published_time") or meta_content(soup, name="date")
    body = ""
    try:
        from trafilatura import extract as trafilatura_extract
        body = (trafilatura_extract(
            html, url=url, output_format="markdown",
            include_links=True, include_images=True, include_tables=True,
        ) or "").strip()
    except ImportError:
        logger.warning("Trafilatura 未安装，临时退回旧正文提取；请重新安装 ingest2md")
    except Exception as exc:
        logger.info("Trafilatura 未取得正文，使用轻量旧逻辑兜底: %s", exc)

    if not body:
        node = _best_content_node(soup)
        # Legacy fallback only: resolve relative links/images before Markdown conversion.
        for el in node.select("a[href]"):
            el["href"] = urljoin(url, el.get("href", ""))
        for el in node.select("img[src]"):
            el["src"] = urljoin(url, el.get("src", ""))
        body = clean_fragment(str(node))
    if not body:
        raise RuntimeError("未能从网页提取可读正文")
    metadata = [("来源", host_of(url))]
    if author:
        metadata.append(("作者", author))
    if published:
        metadata.append(("发布时间", published))
    return Document(title=title, source_url=url, metadata=metadata, body_md=body,
                    source_type="web")
