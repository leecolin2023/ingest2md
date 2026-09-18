"""Transcribe audio into structured segments; never render or parse Markdown."""
from pathlib import Path
from typing import Protocol

from ingest2md.config import Settings
from ingest2md.media.audio import chunk_audio
from ingest2md.transcription.model import Segment, TranscriptResult
from ingest2md.transcription.opencode import OpencodeEngine
from ingest2md.transcription.translation import Translator, make_translator, translate_text
import logging

logger = logging.getLogger(__name__)


class TranscriptionEngine(Protocol):
    def transcribe_chunks(self, chunks: list) -> list: ...


def transcribe_audio(audio_path: str, work_dir: Path, settings: Settings,
                     engine: TranscriptionEngine | None = None,
                     translator: Translator | None = None) -> TranscriptResult:
    chunks = chunk_audio(audio_path, settings.chunk_seconds, settings.limit_seconds,
                         str(work_dir / "chunks"))
    if not chunks:
        raise ValueError("音频过短或没有可转写内容")
    if engine is None:
        engine = OpencodeEngine(settings.api_key, settings.base_url,
                                settings.model, settings.candidates)
    originals = engine.transcribe_chunks(chunks)
    if len(originals) != len(chunks) or any(not item.get("text", "").strip() for item in originals):
        raise ValueError("原语言转写为空或缺少分段，未进入翻译")
    translator = translator or make_translator(settings)
    segments = []
    for index, item in enumerate(originals, 1):
        logger.info("中文翻译 [%s/%s]", index, len(originals))
        translated = translate_text(item["text"], translator)
        segments.append(Segment(item["start"], item["end"], translated, item["text"]))
    return TranscriptResult(segments, list(getattr(engine, "used_models", [])),
                            chunks[-1]["end"],
                            translation_models=list(getattr(translator, "used_models", [])))
