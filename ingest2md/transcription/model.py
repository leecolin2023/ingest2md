"""Transcription data independent of Markdown formatting."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    start: float
    end: float
    text: str
    raw_text: str = ""


@dataclass
class NormalizationReport:
    mode: str = "off"
    model: str = ""
    processed_segments: int = 0
    changed_segments: int = 0
    hints_used: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class TranscriptResult:
    segments: list[Segment]
    models: list[str]
    processed_seconds: float
    timestamp_precision: str = "chunk"
    language: str = ""
    normalization: NormalizationReport | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(
            segment.text.strip()
            for segment in self.segments
            if segment.text.strip()
        )
