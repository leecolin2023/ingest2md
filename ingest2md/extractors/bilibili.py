"""Bilibili channel using the in-package structured transcription pipeline."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ingest2md.config import Settings, load_settings
from ingest2md.media import bilibili as source
from ingest2md.media.audio import _ffmpeg_bin
from ingest2md.model import Document
from ingest2md.extractors.video import localize_metadata, retain_media
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.writers import render_markdown
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)
_BILIBILI_HOSTS = {"www.bilibili.com", "bilibili.com", "m.bilibili.com", "b23.tv"}


class BilibiliExtractor:
    name = "Bilibili 视频转写"
    description = "bilibili.com / b23.tv / BV号 → 音频转写和本地 Markdown"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def match(self, url: str) -> bool:
        return host_of(url) in _BILIBILI_HOSTS or bool(source.BV_RE.fullmatch(url))

    async def extract(self, url: str, output_dir: Path) -> Document:
        return await asyncio.to_thread(self._extract, url, output_dir)

    def _extract(self, url: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        if not settings.api_key:
            raise ValueError("未配置 API Key；请设置 OPENCODE_API_KEY 或使用 --config")
        _ffmpeg_bin("ffmpeg")
        _ffmpeg_bin("ffprobe")
        cookies_file = settings.bilibili_cookies_file or settings.cookies_file
        if cookies_file and not Path(cookies_file).expanduser().is_file():
            raise ValueError(f"Cookie 文件不存在: {cookies_file}")
        bvid, part = source.resolve_video(url)
        meta = source.fetch_meta(bvid, part)
        logger.info("视频: %s；开始下载、切段和转写（会消耗 API 额度）", meta["title"])
        with tempfile.TemporaryDirectory(prefix="ingest2md-bili-") as temp:
            work = Path(temp)
            audio_path = source.download_audio(bvid, temp, cookies_file, part)
            transcript = transcribe_audio(audio_path, work, settings)
            source_id = f"{bvid}_p{part}"
            metadata = [
                ("UP主", meta["uploader"]),
                ("时长（秒）", str(meta["duration"])),
                ("已处理（秒）", str(transcript.processed_seconds)),
                ("转写时间", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                ("模型", ", ".join(transcript.models)),
                ("时间戳精度", "切段级，非逐句；模型转写可能有误差"),
            ]
            body = render_markdown(transcript)
            doc = Document(title=meta["title"], source_url=meta["url"],
                           metadata=metadata, body_md=body, transcript=transcript,
                           source_id=source_id, source_type="bilibili")
            localize_metadata(doc, meta.get("desc", ""), settings)
            retain_media(doc, audio_path, work, output_dir, settings)
            return doc
