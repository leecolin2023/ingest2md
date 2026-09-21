"""Xiaoyuzhou public episode -> Show Notes + shared transcription pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ingest2md.config import Settings, load_settings
from ingest2md.extractors.video import retain_media
from ingest2md.htmlutils import clean_fragment, meta_content, text_of_html
from ingest2md.netutils import DEFAULT_USER_AGENT
from ingest2md.media.download import download_url
from ingest2md.model import Document
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.writers import render_markdown
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)
_HOSTS = {"xiaoyuzhoufm.com", "www.xiaoyuzhoufm.com"}
_EPISODE_RE = re.compile(r"/episode/([0-9a-fA-F]{24})(?:/|$)")
_AUDIO_RE = re.compile(r"https://media\.xyzcdn\.net/[^\"'\\\s<>]+\.(?:m4a|mp3|aac|wav)(?:\?[^\"'\\\s<>]*)?", re.I)

class XiaoyuzhouExtractor:
    name = "小宇宙播客"
    description = "xiaoyuzhoufm.com/episode 单集 → Show Notes + 播客转写 Markdown"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def match(self, url: str) -> bool:
        return host_of(url) in _HOSTS and bool(_EPISODE_RE.search(urlparse(url).path))

    async def extract(self, url: str, output_dir: Path) -> Document:
        return await asyncio.to_thread(self._extract, url, output_dir)

    def _extract(self, url: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        html = fetch_episode_page(url)
        meta = parse_episode_page(html, url)
        logger.info("小宇宙单集: %s；下载音频并使用 %s 转写", meta["title"], settings.asr_backend)

        with tempfile.TemporaryDirectory(prefix="ingest2md-xiaoyuzhou-") as temp:
            work = Path(temp)
            suffix = _audio_suffix(meta["audio_url"])
            audio_path = download_url(meta["audio_url"], work / f"audio{suffix}")
            runtime = getattr(self, "runtime", None)
            backend = runtime.get_asr_backend() if runtime is not None else None
            transcript = transcribe_audio(str(audio_path), work, settings, backend=backend)

            metadata = [("来源", "小宇宙")]
            if meta["podcast_title"]:
                metadata.append(("播客", meta["podcast_title"]))
            if meta["duration"]:
                metadata.append(("时长", _human_duration(meta["duration"])))
            if meta["pub_date"]:
                metadata.append(("发布时间", meta["pub_date"]))
            metadata.extend([
                ("已处理（秒）", str(transcript.processed_seconds)),
                ("转写时间", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                ("ASR 后端", settings.asr_backend),
                ("转写模型", ", ".join(transcript.models)),
                ("语言", transcript.language or "原语言"),
                ("输出", "原语言转写（未翻译）"),
                ("时间戳精度", transcript.timestamp_precision),
            ])

            body_parts: list[str] = []
            description = meta["description"].strip()
            shownotes = meta["shownotes_md"].strip()
            if description and _normalized_text(description) not in _normalized_text(shownotes):
                body_parts.append("## 节目简介\n\n" + description)
            if shownotes:
                body_parts.append("## Show Notes\n\n" + shownotes)
            elif description:
                # Keep the stable section name even for episodes that only expose a description.
                body_parts.append("## Show Notes\n\n" + description)
            body_parts.append("## 转写正文\n\n" + render_markdown(transcript))

            doc = Document(
                title=meta["title"],
                source_url=meta["canonical_url"],
                source_id=meta["episode_id"],
                source_type="xiaoyuzhou",
                metadata=metadata,
                body_md="\n\n".join(body_parts),
                transcript=transcript,
                original_description=description,
            )
            retain_media(doc, str(audio_path), work, output_dir, settings)
            return doc


def fetch_episode_page(url: str) -> str:
    with httpx.Client(
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        follow_redirects=True,
        timeout=25,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _episode_from_next_data(soup: BeautifulSoup) -> dict:
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return {}
    try:
        data = json.loads(script.string)
    except (TypeError, json.JSONDecodeError):
        return {}
    for item in _walk_dicts(data):
        enclosure = item.get("enclosure")
        if not item.get("title") or not enclosure:
            continue
        if isinstance(enclosure, dict) and enclosure.get("url"):
            return item
        if isinstance(enclosure, str) and enclosure.startswith("http"):
            return item
    return {}


def parse_episode_page(html: str, url: str) -> dict[str, object]:
    """Parse public episode metadata without requiring a private API."""
    soup = BeautifulSoup(html, "html.parser")
    episode = _episode_from_next_data(soup)
    path_match = _EPISODE_RE.search(urlparse(url).path)
    episode_id = str(episode.get("eid") or (path_match.group(1) if path_match else ""))

    enclosure = episode.get("enclosure") or {}
    audio_url = enclosure.get("url", "") if isinstance(enclosure, dict) else str(enclosure or "")
    if not audio_url:
        audio_url = meta_content(soup, prop="og:audio")
    if not audio_url:
        match = _AUDIO_RE.search(html)
        audio_url = match.group(0) if match else ""
    if not audio_url:
        raise RuntimeError("未能从小宇宙公开页面取得音频地址；页面结构可能已变化")

    title = str(episode.get("title") or meta_content(soup, prop="og:title") or "小宇宙播客").strip()
    podcast = episode.get("podcast") or {}
    podcast_title = str(podcast.get("title") or "") if isinstance(podcast, dict) else ""
    if not podcast_title:
        # og:title commonly ends with " - 播客名 | 小宇宙"; only use it as a weak fallback.
        page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if " - " in page_title and " | 小宇宙" in page_title:
            podcast_title = page_title.rsplit(" | 小宇宙", 1)[0].rsplit(" - ", 1)[-1].strip()

    raw_shownotes = str(episode.get("shownotes") or "")
    shownotes_md = clean_fragment(raw_shownotes) if raw_shownotes else ""
    description = str(episode.get("description") or "").strip()
    if description and "<" in description and ">" in description:
        description = clean_fragment(description)
    if not description:
        description = meta_content(soup, prop="og:description") or meta_content(soup, name="description")
    if not description and raw_shownotes:
        description = text_of_html(raw_shownotes)

    duration = episode.get("duration") or 0
    try:
        duration = int(float(duration))
    except (TypeError, ValueError):
        duration = 0
    pub_date = str(episode.get("pubDate") or episode.get("pub_date") or "").strip()
    canonical_url = f"https://www.xiaoyuzhoufm.com/episode/{episode_id}" if episode_id else url
    return {
        "episode_id": episode_id,
        "title": title,
        "podcast_title": podcast_title,
        "duration": duration,
        "pub_date": pub_date,
        "audio_url": audio_url,
        "description": description,
        "shownotes_md": shownotes_md,
        "canonical_url": canonical_url,
    }


def _audio_suffix(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".m4a", ".mp3", ".aac", ".wav", ".flac", ".ogg", ".opus"} else ".m4a"


def _human_duration(seconds: int) -> str:
    if seconds >= 3600:
        hours, rem = divmod(seconds, 3600)
        minutes = rem // 60
        return f"{hours}小时{minutes}分钟" if minutes else f"{hours}小时"
    return f"{max(1, round(seconds / 60))}分钟"


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")
