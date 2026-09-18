"""Transcription data independent of Markdown formatting."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    segments: list[Segment]
    models: list[str]
    processed_seconds: float
    timestamp_precision: str = "chunk"
    language: str = ""

    @property
    def text(self) -> str:
        return "\n\n".join(segment.text.strip() for segment in self.segments if segment.text.strip())
