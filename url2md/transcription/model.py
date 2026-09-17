"""Transcription data independent of Markdown formatting."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    start: float
    end: float
    text: str
    original_text: str = ""


@dataclass
class TranscriptResult:
    segments: list[Segment]
    models: list[str]
    processed_seconds: float
    timestamp_precision: str = "chunk"
    output_language: str = "zh-Hans"
    translation_models: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text.strip() for s in self.segments)
