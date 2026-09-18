"""B站链接解析、视频元信息获取与音频下载。"""

import re
import requests
from urllib.parse import parse_qs, urlparse

from ingest2md.netutils import DEFAULT_USER_AGENT

VIEW_API = "https://api.bilibili.com/x/web-interface/view"

HEADERS = {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://www.bilibili.com/"}

BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")


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


def fetch_meta(bvid: str, part: int = 1) -> dict:
    """获取视频元信息：标题、UP主、时长、简介。"""
    resp = requests.get(VIEW_API, params={"bvid": bvid}, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取视频信息失败: {data.get('message')}")
    d = data["data"]
    pages = d.get("pages") or [{"page": 1, "duration": d["duration"]}]
    page = next((p for p in pages if p["page"] == part), None)
    if page is None:
        raise ValueError(f"视频没有第 {part} P")
    return {
        "bvid": bvid,
        "part": part,
        "title": d["title"] + (f" - P{part} {page.get('part', '')}" if len(pages) > 1 else ""),
        "uploader": d["owner"]["name"],
        "duration": page["duration"],
        "desc": (d.get("desc") or "").strip(),
        "url": f"https://www.bilibili.com/video/{bvid}?p={part}",
    }


def download_audio(bvid: str, out_dir: str, cookies_file: str = "", part: int = 1) -> str:
    """用 yt-dlp 下载最佳音轨，返回音频文件路径。"""
    import yt_dlp

    opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{out_dir}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.bilibili.com/video/{bvid}?p={part}", download=True)
        path = ydl.prepare_filename(info)
    return path
