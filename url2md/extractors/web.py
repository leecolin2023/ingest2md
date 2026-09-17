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

from url2md.browser import launch_chromium
from url2md.htmlutils import clean_fragment
from url2md.model import Document
from url2md.urlutils import host_of

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


class GenericWebExtractor:
    name = "普通网页"
    description = "普通 http/https 网页 → 主正文 Markdown"

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
        html, final_url = await _fetch_browser(url)
        return parse_web_page(html, final_url)


async def _fetch_http(url: str) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        follow_redirects=True,
        timeout=20,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def _fetch_browser(url: str) -> tuple[str, str]:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await launch_chromium(p, headless=True)
        context = await browser.new_context(user_agent=_USER_AGENT, locale="zh-CN")
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(1200)
        html = await page.content()
        final_url = page.url
        await browser.close()
    return html, final_url


def _meta(soup: BeautifulSoup, *keys: tuple[str, str]) -> str:
    for attr, value in keys:
        node = soup.find("meta", attrs={attr: value})
        if node and node.get("content"):
            return node["content"].strip()
    return ""


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
        _meta(soup, ("property", "og:title"), ("name", "twitter:title"))
        or (soup.title.get_text(" ", strip=True) if soup.title else "")
        or host_of(url)
        or "网页"
    )
    author = _meta(soup, ("name", "author"), ("property", "article:author"))
    published = _meta(soup, ("property", "article:published_time"), ("name", "date"))
    node = _best_content_node(soup)
    # Resolve relative links/images before Markdown conversion.
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
