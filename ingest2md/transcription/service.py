"""Choose one ASR backend; the backend owns preprocessing and chunking."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ingest2md.config import Settings
from ingest2md.transcription.model import TranscriptResult
from ingest2md.transcription.normalization import NormalizationHints, normalize_transcript


class ASRBackend(Protocol):
    def transcribe(self, audio_path: str, work_dir: Path, settings: Settings) -> TranscriptResult: ...


def create_asr_backend(settings: Settings) -> ASRBackend:
    if settings.asr_backend == "sensevoice":
        from ingest2md.transcription.sensevoice import SenseVoiceBackend
        return SenseVoiceBackend()
    if settings.asr_backend == "openai":
        from ingest2md.transcription.openai_asr import OpenAIASRBackend
        return OpenAIASRBackend()
    if settings.asr_backend == "llm":
        from ingest2md.transcription.llm_audio import LLMAudioBackend
        return LLMAudioBackend()
    raise ValueError(f"不支持的 ASR backend: {settings.asr_backend}")


def transcribe_audio(
    audio_path: str,
    work_dir: Path,
    settings: Settings,
    backend: ASRBackend | None = None,
    hints: NormalizationHints | None = None,
) -> TranscriptResult:
    backend = backend or create_asr_backend(settings)
    result = backend.transcribe(audio_path, work_dir, settings)
    if not result.segments or not result.text.strip():
        raise ValueError("ASR 未返回可读转写内容")
    return normalize_transcript(result, settings, hints=hints)
