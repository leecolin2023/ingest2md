"""Lightweight subtitle acquisition through yt-dlp.

This module deliberately does not broaden ingest2md's public platform support.
It is only a reusable backend for source adapters that have already matched a
known media source such as YouTube or Bilibili.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


@dataclass
class SubtitleTrack:
    language: str
    kind: str  # "manual" or "auto"
    cues: list[SubtitleCue]


_PREFERRED_LANGUAGES = (
    "zh-Hans", "zh-CN", "zh", "zh-TW", "zh-Hant",
    "en", "en-US", "en-GB",
)
_TIMESTAMP_RE = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[.,](?P<ms>\d{3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


def _cookie_options(cookies_file: str) -> dict:
    if not cookies_file:
        return {}
    path = Path(cookies_file).expanduser()
    if not path.is_file():
        raise ValueError(f"Cookie 文件不存在: {path}")
    return {"cookiefile": str(path)}


def _pick_language(tracks: dict) -> str:
    if not tracks:
        return ""
    for preferred in _PREFERRED_LANGUAGES:
        if preferred in tracks:
            return preferred
    lower_map = {key.lower(): key for key in tracks}
    for preferred in _PREFERRED_LANGUAGES:
        match = lower_map.get(preferred.lower())
        if match:
            return match
    return next(iter(tracks))


def _time_value(value: str) -> float:
    match = _TIMESTAMP_RE.search(value.strip())
    if not match:
        raise ValueError(f"无法解析字幕时间戳: {value}")
    return (
        int(match.group("h")) * 3600
        + int(match.group("m")) * 60
        + int(match.group("s"))
        + int(match.group("ms")) / 1000
    )


def parse_vtt_or_srt(text: str) -> list[SubtitleCue]:
    """Parse the common VTT/SRT subset emitted by yt-dlp.

    Styling/positioning markup is intentionally discarded; ingest2md only needs
    readable text and cue timing for its portable Markdown contract.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[SubtitleCue] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        left, right = line.split("-->", 1)
        try:
            start = _time_value(left)
            end = _time_value(right)
        except ValueError:
            i += 1
            continue
        i += 1
        payload: list[str] = []
        while i < len(lines) and lines[i].strip():
            cleaned = _TAG_RE.sub("", lines[i]).strip()
            if cleaned:
                payload.append(html.unescape(cleaned))
            i += 1
        cue_text = " ".join(payload).strip()
        if cue_text and (not cues or cues[-1].text != cue_text):
            cues.append(SubtitleCue(start, end, cue_text))
        i += 1
    return cues


def fetch_yt_dlp_subtitles(url: str, work_dir: Path, cookies_file: str = "") -> SubtitleTrack | None:
    """Fetch one best subtitle track without downloading media."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise ImportError("字幕探测需要 yt-dlp，请重新安装 ingest2md") from exc

    probe_options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        **_cookie_options(cookies_file),
    }
    with yt_dlp.YoutubeDL(probe_options) as ydl:
        info = ydl.extract_info(url, download=False)

    manual = {
        key: value for key, value in ((info or {}).get("subtitles") or {}).items()
        if key.lower() != "danmaku"
    }
    automatic = (info or {}).get("automatic_captions") or {}
    if manual:
        kind, tracks = "manual", manual
    elif automatic:
        kind, tracks = "auto", automatic
    else:
        return None

    language = _pick_language(tracks)
    if not language:
        return None

    work_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(work_dir / "subtitle.%(ext)s")
    download_options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": outtmpl,
        "subtitleslangs": [language],
        "subtitlesformat": "vtt/srt/best",
        "writesubtitles": kind == "manual",
        "writeautomaticsub": kind == "auto",
        **_cookie_options(cookies_file),
    }
    before = {p.resolve() for p in work_dir.iterdir() if p.is_file()}
    with yt_dlp.YoutubeDL(download_options) as ydl:
        ydl.extract_info(url, download=True)
    candidates = [
        p for p in work_dir.iterdir()
        if p.is_file() and p.resolve() not in before and p.suffix.lower() in {".vtt", ".srt"}
    ]
    if not candidates:
        candidates = [p for p in work_dir.iterdir() if p.suffix.lower() in {".vtt", ".srt"}]
    if not candidates:
        return None
    subtitle_path = max(candidates, key=lambda p: p.stat().st_mtime)
    cues = parse_vtt_or_srt(subtitle_path.read_text(encoding="utf-8", errors="replace"))
    if not cues:
        return None
    return SubtitleTrack(language=language, kind=kind, cues=cues)
