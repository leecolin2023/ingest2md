"""Existing local audio/video -> selected ASR backend -> Markdown."""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ingest2md.config import Settings, load_settings
from ingest2md.media.audio import probe_duration
from ingest2md.model import Document
from ingest2md.transcription.service import transcribe_audio
from ingest2md.transcription.writers import render_markdown

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


class LocalMediaExtractor:
    name = "本地音视频"
    description = "本地音视频 → 默认 SenseVoice 本地转写 → 原语言 Markdown"
    acquisition_plan = (
        "识别本地音视频",
        "使用配置的 ASR backend（默认 SenseVoice ONNX 本地）",
        "保留原语言转写，不做强制翻译",
        "输出 portable Markdown",
    )

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def match(self, reference: str) -> bool:
        try:
            path = Path(reference).expanduser()
            return path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
        except (OSError, ValueError):
            return False

    async def extract(self, reference: str, output_dir: Path) -> Document:
        return await asyncio.to_thread(self._extract, reference, output_dir)

    def _extract(self, reference: str, output_dir: Path) -> Document:
        settings = self.settings or load_settings()
        path = Path(reference).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ValueError(f"不是受支持的本地音视频文件: {path}")

        media_kind = "本地音频" if path.suffix.lower() in AUDIO_EXTENSIONS else "本地视频"
        with tempfile.TemporaryDirectory(prefix="ingest2md-local-") as temp:
            work = Path(temp)
            transcript = transcribe_audio(str(path), work, settings)
            try:
                duration = probe_duration(str(path))
            except Exception:
                duration = 0
            metadata = [
                ("来源", media_kind),
                ("文件", path.name),
                ("ASR 后端", settings.asr_backend),
                ("时长（秒）", str(round(duration, 2)) if duration else ""),
                ("已处理（秒）", str(transcript.processed_seconds)),
                ("转写时间", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                ("转写模型", ", ".join(transcript.models)),
                ("语言", transcript.language or "原语言"),
                ("输出", "原语言转写（未翻译）"),
                ("时间戳精度", transcript.timestamp_precision),
            ]
            doc = Document(
                title=path.stem,
                source_url=path.as_uri(),
                source_type="local_media",
                metadata=metadata,
                body_md="## 转写正文\n\n" + render_markdown(transcript),
                transcript=transcript,
            )
            self._retain_optional_files(doc, path, work, output_dir, settings)
            return doc

    @staticmethod
    def _retain_optional_files(doc: Document, source_path: Path, work: Path,
                               output_dir: Path, settings: Settings) -> None:
        doc_dir = output_dir / doc.dirname
        if settings.keep_audio:
            doc_dir.mkdir(parents=True, exist_ok=True)
            filename = "source_media" + source_path.suffix.lower()
            shutil.copy2(source_path, doc_dir / filename)
            doc.attachments.append(filename)
        if settings.keep_chunks:
            for chunk in sorted((work / "chunks").glob("*")):
                if not chunk.is_file():
                    continue
                target = doc_dir / "chunks" / chunk.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(chunk, target)
                doc.attachments.append(f"chunks/{chunk.name}")
