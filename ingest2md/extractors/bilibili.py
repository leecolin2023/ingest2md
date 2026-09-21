"""Bilibili -> subtitle-first ingestion -> selected ASR fallback."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ingest2md.config import Settings, load_settings
from ingest2md.extractors.video import attach_video_description, retain_media
from ingest2md.media import bilibili as source
from ingest2md.media.subtitles import fetch_yt_dlp_subtitles
from ingest2md.model import Document
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.subtitles import subtitles_to_transcript
from ingest2md.transcription.writers import render_markdown
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)
_BILIBILI_HOSTS = {"www.bilibili.com", "bilibili.com", "m.bilibili.com", "b23.tv"}


class BilibiliExtractor:
    name = "Bilibili 视频"
    description = "Bilibili / BV号 → 字幕优先；无字幕时默认 SenseVoice 本地 ASR"
    acquisition_plan = (
        "解析 BV 号和分 P",
        "优先探测平台字幕",
        "有字幕则直接保留原语言，不调用 ASR/LLM",
        "无字幕时使用配置 ASR backend（默认 SenseVoice ONNX 本地）",
    )

    def __init__(self, settings: Settings | None = None, runtime=None):
        self.settings = settings
        self.runtime = runtime

    def match(self, url: str) -> bool:
        return host_of(url) in _BILIBILI_HOSTS or bool(source.BV_RE.fullmatch(url))

    async def extract(self, url: str, output_dir: Path) -> Document:
        return await asyncio.to_thread(self._extract, url, output_dir)

    def _extract(self, url: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        cookies_file = settings.bilibili_cookies_file or settings.cookies_file
        if cookies_file and not Path(cookies_file).expanduser().is_file():
            raise ValueError(f"Cookie 文件不存在: {cookies_file}")

        bvid, part = source.resolve_video(url)
        meta = source.fetch_meta(bvid, part)
        with tempfile.TemporaryDirectory(prefix="ingest2md-bili-") as temp:
            work = Path(temp)
            try:
                track = fetch_yt_dlp_subtitles(meta["url"], work / "subtitles", cookies_file)
            except Exception as exc:
                logger.info("字幕探测失败，继续 ASR fallback: %s", exc)
                track = None

            audio_path = ""
            if track is not None:
                logger.info("找到 Bilibili %s 字幕（%s），跳过 ASR", track.kind, track.language)
                transcript = subtitles_to_transcript(track, settings)
                acquisition = f"平台字幕（{track.kind}, {track.language}）"
                if settings.keep_audio:
                    audio_path = source.download_audio(bvid, temp, cookies_file, part)
            else:
                logger.info("未找到可用字幕；下载 Bilibili 音频并使用 %s ASR", settings.asr_backend)
                audio_path = source.download_audio(bvid, temp, cookies_file, part)
                transcript = (
                    transcribe_audio(audio_path, work, settings, backend=self.runtime.asr_backend)
                    if self.runtime is not None
                    else transcribe_audio(audio_path, work, settings)
                )
                acquisition = f"音频下载 + {settings.asr_backend} ASR fallback"

            doc = Document(
                title=meta["title"],
                source_url=meta["url"],
                metadata=[
                    ("UP主", meta["uploader"]),
                    ("时长（秒）", str(meta["duration"])),
                    ("内容获取", acquisition),
                    ("已处理（秒）", str(transcript.processed_seconds)),
                    ("处理时间", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                    ("转写/字幕来源", ", ".join(transcript.models)),
                    ("语言", transcript.language or "原语言"),
                    ("时间戳精度", transcript.timestamp_precision),
                ],
                body_md=render_markdown(transcript, window_seconds=settings.transcript_window_seconds),
                transcript=transcript,
                source_id=f"{bvid}_p{part}",
                source_type="bilibili",
            )
            attach_video_description(doc, meta.get("desc", ""))
            if audio_path:
                retain_media(doc, audio_path, work, output_dir, settings)
            return doc
