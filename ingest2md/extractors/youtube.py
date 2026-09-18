"""YouTube → original-language transcription → Chinese archive."""
import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ingest2md.config import Settings, load_settings
from ingest2md.extractors.video import localize_metadata, retain_media
from ingest2md.media import youtube as source
from ingest2md.media.audio import _ffmpeg_bin
from ingest2md.model import Document
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.writers import render_markdown
from ingest2md.urlutils import host_of

logger = logging.getLogger(__name__)


class YouTubeExtractor:
    name = "YouTube 视频转写"
    description = "youtube.com / youtu.be 视频 → 原语言转写 → 中文 Markdown"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def match(self, url: str) -> bool:
        return host_of(url) in source.HOSTS

    async def extract(self, url: str, output_dir: Path) -> Document:
        return await asyncio.to_thread(self._extract, url, output_dir)

    def _extract(self, url: str, output_dir: Path) -> Document:
        url = source.normalize_video_url(url)
        settings = self.settings or load_settings()
        if not settings.api_key:
            raise ValueError("未配置 API Key；请设置 OPENCODE_API_KEY 或使用 --config")
        _ffmpeg_bin("ffmpeg")
        _ffmpeg_bin("ffprobe")
        cookies_file = settings.youtube_cookies_file or settings.cookies_file
        if cookies_file and not Path(cookies_file).expanduser().is_file():
            raise ValueError(f"Cookie 文件不存在: {cookies_file}")
        logger.info("下载 YouTube 音频；随后转写并翻译为中文（会消耗 API 额度）")
        with tempfile.TemporaryDirectory(prefix="ingest2md-youtube-") as temp:
            work = Path(temp)
            meta, audio_path = source.download_video(url, work, cookies_file)
            transcript = transcribe_audio(audio_path, work, settings)
            doc = Document(
                title=meta["title"], source_url=meta["url"],
                source_id=meta["id"], source_type="youtube", transcript=transcript,
                body_md=render_markdown(transcript),
                metadata=[("频道", meta["uploader"]), ("时长（秒）", str(meta["duration"])),
                          ("已处理（秒）", str(transcript.processed_seconds)),
                          ("转写时间", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                          ("转写模型", ", ".join(transcript.models)),
                          ("时间戳精度", "切段级，非逐句；转写与翻译可能有误差")],
            )
            localize_metadata(doc, meta["desc"], settings)
            retain_media(doc, audio_path, work, output_dir, settings)
            return doc
