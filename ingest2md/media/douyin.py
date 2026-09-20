"""Douyin single-video acquisition through an existing browser session.

This deliberately avoids private signing APIs (a_bogus/X-Bogus). The adapter
lets the rendered page do its own JavaScript work and only consumes a direct
http(s) media URL already exposed by the DOM.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from ingest2md.browser import load_netscape_cookies, launch_chromium
from ingest2md.netutils import DEFAULT_USER_AGENT
from ingest2md.urlutils import host_of

HOSTS = {
    "douyin.com", "www.douyin.com", "v.douyin.com",
    "iesdouyin.com", "www.iesdouyin.com",
}
_VIDEO_ID_RE = re.compile(r"/video/(\d+)")


def is_douyin_url(url: str) -> bool:
    host = host_of(url)
    return host in HOSTS or host.endswith(".douyin.com")


def normalize_page_snapshot(snapshot: dict, final_url: str) -> dict:
    """Choose one directly downloadable DOM media URL and normalize metadata."""
    candidates = [
        snapshot.get("current_src", ""),
        snapshot.get("src", ""),
        *(snapshot.get("sources") or []),
    ]
    media_url = ""
    saw_blob = False
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        if value.startswith("blob:"):
            saw_blob = True
            continue
        resolved = urljoin(final_url, value)
        if resolved.startswith(("http://", "https://")):
            media_url = resolved
            break

    canonical_url = str(snapshot.get("canonical_url") or final_url).strip() or final_url
    match = _VIDEO_ID_RE.search(urlparse(canonical_url).path) or _VIDEO_ID_RE.search(
        urlparse(final_url).path
    )
    return {
        "video_id": match.group(1) if match else "",
        "title": str(snapshot.get("title") or "抖音视频").strip() or "抖音视频",
        "author": str(snapshot.get("author") or "").strip(),
        "description": str(snapshot.get("description") or "").strip(),
        "canonical_url": canonical_url,
        "media_url": media_url,
        "saw_blob": saw_blob,
    }


async def resolve_video_page(url: str, cookies_file: str = "") -> dict:
    """Open one public Douyin video page and return DOM-exposed media metadata."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await launch_chromium(p, headless=True)
        context = await browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="zh-CN",
        )
        try:
            if cookies_file:
                cookies = load_netscape_cookies(cookies_file, "douyin.com")
                if cookies:
                    await context.add_cookies(cookies)

            page = await context.new_page()
            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )
            except Exception as exc:
                raise RuntimeError(f"抖音页面访问失败: {exc}") from exc

            if response and response.status >= 400:
                raise RuntimeError(f"抖音页面访问失败: HTTP {response.status}")

            await page.wait_for_timeout(1800)
            try:
                await page.wait_for_function(
                    """() => {
                        const v = document.querySelector('video');
                        if (!v) return false;
                        const urls = [v.currentSrc, v.src,
                          ...Array.from(v.querySelectorAll('source')).map(x => x.src)];
                        return urls.some(u => u && /^https?:\/\//i.test(u));
                    }""",
                    timeout=10_000,
                )
            except Exception:
                # Keep going: the final snapshot may still expose src/source attrs,
                # or it may tell us that only a blob URL/login wall is visible.
                pass

            snapshot = await page.evaluate(
                """() => {
                    const v = document.querySelector('video');
                    const meta = (selector) =>
                        document.querySelector(selector)?.getAttribute('content') || '';
                    const firstText = (selectors) => {
                        for (const selector of selectors) {
                            const node = document.querySelector(selector);
                            const text = (node?.textContent || '').trim();
                            if (text) return text;
                        }
                        return '';
                    };
                    return {
                        current_src: v?.currentSrc || '',
                        src: v?.src || '',
                        sources: v ? Array.from(v.querySelectorAll('source'))
                            .map(x => x.src || x.getAttribute('src') || '').filter(Boolean) : [],
                        title: meta('meta[property="og:title"]') ||
                               meta('meta[name="twitter:title"]') ||
                               document.title || '',
                        description: meta('meta[property="og:description"]') ||
                                     meta('meta[name="description"]') || '',
                        author: firstText([
                            '[data-e2e="video-author-name"]',
                            '[data-e2e="author-name"]',
                            '.account-name',
                            '.author-name'
                        ]),
                        canonical_url: document.querySelector('link[rel="canonical"]')?.href || ''
                    };
                }"""
            )
            final_url = page.url
            meta = normalize_page_snapshot(snapshot or {}, final_url)

            browser_cookies = await context.cookies()
            if browser_cookies:
                meta["cookie_header"] = "; ".join(
                    f"{item['name']}={item['value']}"
                    for item in browser_cookies
                    if item.get("name") and item.get("value") is not None
                )
            else:
                meta["cookie_header"] = ""
        finally:
            await browser.close()

    if not meta["media_url"]:
        reason = "页面只暴露 blob 媒体地址" if meta.get("saw_blob") else "页面 DOM 中没有直接媒体地址"
        cookie_hint = (
            "当前已提供 Cookie，但页面仍未暴露可下载媒体地址。"
            if cookies_file else
            "可尝试提供 --douyin-cookies-file 登录 Cookie。"
        )
        raise RuntimeError(
            f"已识别抖音视频，但{reason}。{cookie_hint}"
            "也可以先下载视频，再执行 ingest2md \"/path/to/douyin.mp4\"。"
        )
    return meta
