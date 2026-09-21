"""YouTube -> true subtitle-first ingestion -> selected ASR fallback."""
import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ingest2md.config import Settings, load_settings
from ingest2md.extractors.video import attach_video_description, retain_media
from ingest2md.identity import SourceIdentity
from ingest2md.media import youtube as source
from ingest2md.media.subtitles import fetch_yt_dlp_subtitles_with_info
from ingest2md.model import Document
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.subtitles import subtitles_to_transcript
from ingest2md.transcription.presentation import present_transcript
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)


class YouTubeExtractor:
    name = "YouTube 视频"
    description = "YouTube → 真正字幕优先；无字幕时默认 SenseVoice 本地 ASR"
    acquisition_plan = (
        "直接探测平台人工/自动字幕，不先做音频播放 probe",
        "有字幕则复用同一次 yt-dlp info 作为元数据并直接输出",
        "无字幕时才下载音频",
        "使用配置 ASR backend（默认 SenseVoice ONNX 本地）",
    )

    def __init__(self, settings: Settings | None = None, runtime=None):
        self.settings = settings
        self.runtime = runtime

    def match(self, url: str) -> bool:
        return host_of(url) in source.HOSTS

    async def identity(self, url: str) -> SourceIdentity:
        normalized = source.normalize_video_url(url)
        video_id = parse_qs(urlparse(normalized).query).get("v", [""])[0]
        return SourceIdentity(f"youtube:{video_id}", "youtube", video_id)

    async def extract(self, url: str, output_dir: Path) -> Document:
        return await asyncio.to_thread(self._extract, url, output_dir)

    def _extract(self, url: str, output_dir: Path) -> Document:
        url = source.normalize_video_url(url)
        settings = self.settings or load_settings()
        video_id = parse_qs(urlparse(url).query).get("v", [""])[0]
        cache_key = f"youtube:{video_id}"
        cache = (
            self.runtime.media_cache
            if self.runtime is not None and settings.media_cache_enabled
            else None
        )
        cached_audio = cache.get(cache_key) if cache is not None else None
        cookies_file = settings.youtube_cookies_file or settings.cookies_file
        if cookies_file and not Path(cookies_file).expanduser().is_file():
            raise ValueError(f"Cookie 文件不存在: {cookies_file}")

        with tempfile.TemporaryDirectory(prefix="ingest2md-youtube-") as temp:
            work = Path(temp)
            subtitle_result = None
            try:
                subtitle_result = fetch_yt_dlp_subtitles_with_info(
                    url,
                    work / "subtitles",
                    cookies_file,
                    ydl_options=source.youtube_ydl_options(cookies_file),
                )
            except Exception as exc:
                logger.info("YouTube 字幕探测失败，继续音频 ASR fallback: %s", exc)

            audio_path = ""
            if subtitle_result is not None and subtitle_result.track is not None:
                track = subtitle_result.track
                logger.info("找到 YouTube %s 字幕（%s），跳过音频 probe/ASR", track.kind, track.language)
                meta = source.metadata_from_info(subtitle_result.info, url)
                transcript = subtitles_to_transcript(track, settings)
                acquisition = f"平台字幕（{track.kind}, {track.language}）"
                if settings.keep_audio:
                    # Explicit media retention is allowed to perform a real audio download.
                    if cached_audio is not None:
                        audio_path = str(cached_audio)
                    else:
                        _, audio_path = source.download_video(url, work, cookies_file)
                        if cache is not None:
                            audio_path = str(cache.store(cache_key, audio_path))
            else:
                logger.info("未取得可用字幕；此时才下载 YouTube 音频并使用 %s ASR", settings.asr_backend)
                if cached_audio is not None and subtitle_result is not None:
                    meta = source.metadata_from_info(subtitle_result.info, url)
                    audio_path = str(cached_audio)
                    logger.info("YouTube：复用上次失败任务留下的媒体缓存")
                else:
                    meta, audio_path = source.download_video(url, work, cookies_file)
                    if cache is not None:
                        audio_path = str(cache.store(cache_key, audio_path))
                transcript = (
                    transcribe_audio(audio_path, work, settings, backend=self.runtime.asr_backend)
                    if self.runtime is not None
                    else transcribe_audio(audio_path, work, settings)
                )
                acquisition = f"音频下载 + {settings.asr_backend} ASR fallback"

            doc = Document(
                title=meta["title"],
                source_url=meta["url"],
                source_id=meta["id"],
                source_type="youtube",
                transcript=transcript,
                body_md=present_transcript(transcript, settings),
                metadata=[
                    ("频道", meta["uploader"]),
                    ("时长（秒）", str(meta["duration"])),
                    ("内容获取", acquisition),
                    ("已处理（秒）", str(transcript.processed_seconds)),
                    ("处理时间", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                    ("转写/字幕来源", ", ".join(transcript.models)),
                    ("语言", transcript.language or "原语言"),
                    ("时间戳精度", transcript.timestamp_precision),
                ],
            )
            attach_video_description(doc, meta.get("desc", ""))
            if audio_path:
                retain_media(doc, audio_path, work, output_dir, settings)
            return doc
