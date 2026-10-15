"""B站链接解析、视频元信息获取与音频下载。"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlparse

import requests

from ingest2md.netutils import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

VIEW_API = "https://api.bilibili.com/x/web-interface/view"
HEADERS = {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://www.bilibili.com/"}
BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")


class BilibiliMetaUnavailableError(RuntimeError):
    """The official metadata path is unavailable and may use yt-dlp fallback."""


def resolve_video(value: str) -> tuple[str, int]:
    """Resolve short links while preserving the selected video part."""
    value = value.strip()
    if BV_RE.fullmatch(value):
        return value, 1
    parsed = urlparse(value)
    if parsed.hostname == "b23.tv":
        response = requests.get(value, headers=HEADERS, allow_redirects=True, timeout=30)
        response.raise_for_status()
        value = response.url
        parsed = urlparse(value)
    match = BV_RE.search(parsed.path)
    if not match:
        raise ValueError(f"无法从输入解析出 BV 号: {value}")
    try:
        part = int(parse_qs(parsed.query).get("p", ["1"])[0])
    except ValueError as exc:
        raise ValueError("视频分 P 必须是正整数") from exc
    if part < 1:
        raise ValueError("视频分 P 必须是正整数")
    return match.group(1), part


def fetch_meta(bvid: str, part: int = 1, cookies_file: str = "") -> dict:
    """Fetch metadata with official API first and yt-dlp as access fallback.

    The fallback is only for metadata acquisition failures. Semantic errors such
    as selecting a non-existent part remain explicit instead of being hidden by
    a second acquisition path.
    """
    try:
        return _fetch_meta_from_api(bvid, part)
    except BilibiliMetaUnavailableError as exc:
        logger.info("Bilibili view API 不可用，回退 yt-dlp 元信息解析: %s", exc)
        return _fetch_meta_from_ytdlp(bvid, part, cookies_file=cookies_file)


def _fetch_meta_from_api(bvid: str, part: int = 1) -> dict:
    try:
        resp = requests.get(
            VIEW_API,
            params={"bvid": bvid},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise BilibiliMetaUnavailableError(f"view API 请求失败: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise BilibiliMetaUnavailableError("view API 返回非 JSON 数据") from exc

    if data.get("code") != 0:
        raise BilibiliMetaUnavailableError(
            f"view API 返回错误: {data.get('message') or data.get('code')}"
        )

    try:
        d = data["data"]
        pages = d.get("pages") or [{"page": 1, "duration": d["duration"]}]
    except (KeyError, TypeError) as exc:
        raise BilibiliMetaUnavailableError("view API 元信息结构异常") from exc

    page = next((p for p in pages if p.get("page") == part), None)
    if page is None:
        raise ValueError(f"视频没有第 {part} P")

    owner = d.get("owner") or {}
    return {
        "bvid": bvid,
        "part": part,
        "title": str(d.get("title") or bvid)
        + (f" - P{part} {page.get('part', '')}" if len(pages) > 1 else ""),
        "uploader": str(owner.get("name") or "").strip(),
        "duration": int(page.get("duration") or 0),
        "desc": (d.get("desc") or "").strip(),
        "url": f"https://www.bilibili.com/video/{bvid}?p={part}",
        "metadata_source": "view-api",
    }


def _fetch_meta_from_ytdlp(
    bvid: str,
    part: int = 1,
    cookies_file: str = "",
) -> dict:
    """Fallback metadata path that matches subtitle/audio yt-dlp reachability."""
    import yt_dlp

    url = f"https://www.bilibili.com/video/{bvid}?p={part}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "http_headers": HEADERS,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}

    try:
        duration = int(float(info.get("duration") or 0))
    except (TypeError, ValueError):
        duration = 0

    return {
        "bvid": bvid,
        "part": part,
        "title": str(info.get("title") or bvid).strip(),
        "uploader": str(info.get("uploader") or info.get("channel") or "").strip(),
        "duration": duration,
        "desc": str(info.get("description") or "").strip(),
        "url": url,
        "metadata_source": "yt-dlp",
    }


def download_audio(
    bvid: str,
    out_dir: str,
    cookies_file: str = "",
    part: int = 1,
) -> str:
    """Download the best audio track with resumable, retry-friendly yt-dlp settings."""
    import yt_dlp

    opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{out_dir}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "continuedl": True,
        "retries": 20,
        "fragment_retries": 20,
        "socket_timeout": 60,
        "http_headers": HEADERS,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.bilibili.com/video/{bvid}?p={part}",
            download=True,
        )
        path = ydl.prepare_filename(info)
    return path
