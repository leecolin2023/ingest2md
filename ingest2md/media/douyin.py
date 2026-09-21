"""Douyin single-video acquisition through an existing browser session.

This deliberately avoids generating private signatures (a_bogus/X-Bogus).
The adapter lets the rendered page do its own JavaScript work, consumes media
URLs from the browser's signed detail response, and keeps direct DOM URLs as a
fallback.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

from ingest2md.browser import browser_context, load_netscape_cookies
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


def _url_list(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    urls = value.get("url_list") or []
    if isinstance(urls, str):
        urls = [urls]
    elif isinstance(urls, dict):
        urls = [urls.get("main_url"), urls.get("backup_url"), urls.get("fallback_url")]
    return [str(item).strip() for item in urls if str(item or "").startswith(("http://", "https://"))]


def snapshot_from_aweme_detail(payload: dict) -> dict:
    """Keep only stable metadata/media fields from a browser-fetched detail response."""
    detail = payload.get("aweme_detail") if isinstance(payload, dict) else None
    if not isinstance(detail, dict):
        return {}
    video = detail.get("video") or {}
    music = detail.get("music") or {}
    duration_ms = detail.get("duration") or video.get("duration") or 0
    try:
        duration_seconds = float(duration_ms) / 1000
    except (TypeError, ValueError):
        duration_seconds = 0
    try:
        music_duration = float(music.get("duration") or 0)
    except (TypeError, ValueError):
        music_duration = 0

    # Prefer the final/muxed video so ASR sees the same audio mix as the
    # published work. The music/audio address is only a fallback candidate.
    audio_urls = _url_list(music.get("play_url"))
    video_urls = []
    for key in ("play_addr_h264", "play_addr", "download_addr"):
        video_urls.extend(_url_list(video.get(key)))
    media_candidates = video_urls + audio_urls
    author = detail.get("author") or {}
    return {
        "video_id": str(detail.get("aweme_id") or ""),
        "title": str(detail.get("desc") or "").strip(),
        "description": str(detail.get("desc") or "").strip(),
        "author": str(author.get("nickname") or "").strip(),
        "duration": duration_seconds,
        "media_candidates": list(dict.fromkeys(media_candidates)),
        "acquisition": "Playwright 浏览器详情响应",
    }


def normalize_page_snapshot(snapshot: dict, final_url: str) -> dict:
    """Normalize all browser/detail media candidates instead of trusting the first video."""
    candidates = list(snapshot.get("media_candidates") or [])
    saw_blob = False
    videos = snapshot.get("videos") or []
    if not videos and any(key in snapshot for key in ("current_src", "src", "sources")):
        videos = [snapshot]
    for video in videos:
        candidates.extend([
            video.get("current_src", ""),
            video.get("src", ""),
            *(video.get("sources") or []),
        ])

    media_candidates = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        if value.startswith("blob:"):
            saw_blob = True
            continue
        resolved = urljoin(final_url, value)
        if resolved.startswith(("http://", "https://")) and resolved not in media_candidates:
            media_candidates.append(resolved)

    canonical_url = str(snapshot.get("canonical_url") or final_url).strip() or final_url
    match = _VIDEO_ID_RE.search(urlparse(canonical_url).path) or _VIDEO_ID_RE.search(
        urlparse(final_url).path
    )
    duration = snapshot.get("duration") or 0
    if not duration:
        durations = []
        for video in videos:
            try:
                value = float(video.get("duration") or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                durations.append(value)
        duration = max(durations, default=0)
    return {
        "video_id": match.group(1) if match else "",
        "title": str(snapshot.get("title") or "抖音视频").strip() or "抖音视频",
        "author": str(snapshot.get("author") or "").strip(),
        "description": str(snapshot.get("description") or "").strip(),
        "canonical_url": canonical_url,
        "media_url": media_candidates[0] if media_candidates else "",
        "media_candidates": media_candidates,
        "saw_blob": saw_blob,
        "duration": duration,
        "acquisition": str(snapshot.get("acquisition") or "Playwright DOM 媒体地址"),
    }


async def resolve_video_page(url: str, cookies_file: str = "", browser_runtime=None) -> dict:
    """Open one Douyin page and return browser-resolved media metadata."""
    async with browser_context(
        browser_runtime,
        user_agent=DEFAULT_USER_AGENT,
        locale="zh-CN",
    ) as context:
            if cookies_file:
                cookies = load_netscape_cookies(cookies_file, "douyin.com")
                if cookies:
                    await context.add_cookies(cookies)

            page = await context.new_page()
            detail_snapshots: list[dict] = []
            response_tasks: set[asyncio.Task] = set()
            detail_ready = asyncio.Event()

            async def capture_detail(response):
                if "/aweme/v1/web/aweme/detail/" not in response.url or response.status >= 400:
                    return
                try:
                    detail = snapshot_from_aweme_detail(await response.json())
                    if detail.get("media_candidates"):
                        detail_snapshots.append(detail)
                        detail_ready.set()
                except Exception:
                    return

            def schedule_detail_capture(response):
                task = asyncio.create_task(capture_detail(response))
                response_tasks.add(task)
                task.add_done_callback(response_tasks.discard)

            page.on("response", schedule_detail_capture)
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
                    r"""() => {
                        const videos = Array.from(document.querySelectorAll('video'));
                        const urls = videos.flatMap(v => [v.currentSrc, v.src,
                          ...Array.from(v.querySelectorAll('source')).map(x => x.src)]);
                        return urls.some(u => u && /^https?:\/\//i.test(u));
                    }""",
                    timeout=10_000,
                )
            except Exception:
                # Keep going: the final snapshot may still expose src/source attrs,
                # or it may tell us that only a blob URL/login wall is visible.
                pass

            # A generic placeholder video can appear before the signed detail
            # response. Give the browser response path a short preference window
            # instead of immediately accepting that first DOM URL.
            if not detail_ready.is_set():
                try:
                    await asyncio.wait_for(detail_ready.wait(), timeout=10)
                except TimeoutError:
                    pass

            snapshot = await page.evaluate(
                """() => {
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
                        videos: Array.from(document.querySelectorAll('video')).map(v => ({
                            current_src: v.currentSrc || '',
                            src: v.src || '',
                            sources: Array.from(v.querySelectorAll('source'))
                                .map(x => x.src || x.getAttribute('src') || '').filter(Boolean),
                            duration: Number.isFinite(v.duration) ? v.duration : 0,
                            ready_state: v.readyState
                        })),
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
            if response_tasks:
                await asyncio.gather(*list(response_tasks), return_exceptions=True)
            final_url = page.url
            if detail_snapshots:
                detail = detail_snapshots[-1]
                detail["canonical_url"] = final_url
                detail["videos"] = snapshot.get("videos") or []
                snapshot = {**snapshot, **detail}
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