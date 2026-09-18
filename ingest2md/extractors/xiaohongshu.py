"""Lightweight Xiaohongshu note extractor.

Produces one Markdown plus an images/ directory when note images can be fetched.
It intentionally does not run OCR/Vision in the default fast path.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ingest2md.browser import load_netscape_cookies, launch_chromium
from ingest2md.config import Settings, load_settings
from ingest2md.htmlutils import clean_fragment, meta_content
from ingest2md.netutils import DEFAULT_USER_AGENT
from ingest2md.model import Document, sanitize_filename
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)
_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com", "www.xhslink.com"}

class XiaohongshuExtractor:
    name = "小红书笔记"
    description = "xiaohongshu.com / xhslink.com 笔记 → 正文 + 图片 → Markdown"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def match(self, url: str) -> bool:
        return host_of(url) in _HOSTS

    async def extract(self, url: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await launch_chromium(p, headless=True)
            context = await browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="zh-CN")
            cookie_file = settings.xiaohongshu_cookies_file or settings.cookies_file
            if cookie_file:
                cookies = load_netscape_cookies(cookie_file, "xiaohongshu.com")
                if cookies:
                    await context.add_cookies(cookies)
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=35_000)
            except Exception as exc:
                await browser.close()
                raise RuntimeError(f"小红书页面访问失败: {exc}") from exc
            if response and response.status >= 400:
                await browser.close()
                raise RuntimeError(f"小红书页面访问失败: HTTP {response.status}")
            await page.wait_for_timeout(1800)
            html = await page.content()
            final_url = page.url
            title, author, body, image_urls = parse_note_page(html, final_url)
            if not body:
                await browser.close()
                raise RuntimeError("未能读取小红书笔记正文；可能需要登录 Cookie 或页面结构已变化")
            source_id = _note_id(final_url)
            doc = Document(title=title, source_url=final_url, source_id=source_id,
                           source_type="xiaohongshu", metadata=[("来源", "小红书")], body_md=body)
            if author:
                doc.metadata.append(("作者", author))
            doc_dir = output_dir / doc.dirname
            image_map = await _download_images(context, image_urls, doc_dir / "images")
            if image_map:
                doc.image_map = image_map
                doc.body_md += "\n\n## 图片\n\n" + "\n\n".join(
                    f"![]({relative})" for relative in image_map.values()
                )
            await browser.close()
            return doc


def _note_id(url: str) -> str:
    path = urlparse(url).path
    m = re.search(r"/(?:explore|discovery/item)/(\w+)", path)
    return m.group(1) if m else ""


def parse_note_page(html: str, url: str) -> tuple[str, str, str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = meta_content(soup, prop="og:title") or meta_content(soup, name="twitter:title")
    if not title:
        node = soup.select_one("#detail-title, .title, .note-title")
        title = node.get_text(" ", strip=True) if node else "小红书笔记"
    author_node = soup.select_one(".author .name, .username, .author-name, .user-name")
    author = author_node.get_text(" ", strip=True) if author_node else ""
    body_node = soup.select_one("#detail-desc, .note-text, .desc, .note-content, .content")
    body = clean_fragment(str(body_node)) if body_node else ""
    if not body:
        body = meta_content(soup, prop="og:description") or meta_content(soup, name="description")

    urls = []
    og_image = meta_content(soup, prop="og:image")
    if og_image:
        urls.append(og_image)
    for img in soup.select(".swiper-slide img[src], .note-slider img[src], .carousel img[src], .note-content img[src]"):
        src = img.get("src", "")
        if src and src.startswith("http") and src not in urls:
            urls.append(src)
    return title.strip(), author.strip(), body.strip(), urls[:20]


async def _download_images(context, urls: list[str], image_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not urls:
        return result
    image_dir.mkdir(parents=True, exist_ok=True)
    for index, url in enumerate(urls, 1):
        try:
            response = await context.request.get(url, timeout=15_000)
            if not response.ok:
                continue
            content_type = (response.headers.get("content-type") or "").lower()
            ext = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
            filename = f"{index:02d}{ext}"
            (image_dir / filename).write_bytes(await response.body())
            result[url] = f"images/{filename}"
        except Exception as exc:
            logger.debug("小红书图片下载失败 %s: %s", url, exc)
    if not result:
        try:
            image_dir.rmdir()
        except OSError:
            pass
    return result
