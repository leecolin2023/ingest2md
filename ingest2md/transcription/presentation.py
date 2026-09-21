"""Transcript presentation independent from ASR chunking."""
from __future__ import annotations

from ingest2md.config import Settings
from ingest2md.transcription.enhancer import enhance_markdown
from ingest2md.transcription.model import TranscriptResult
from ingest2md.transcription.writers import render_chaptered_markdown, render_markdown


def present_transcript(
    transcript: TranscriptResult,
    settings: Settings,
    *,
    chapters: list[tuple[float, str]] | None = None,
) -> str:
    """Render readable Markdown, then optionally correct presentation text.

    Raw TranscriptResult remains the source for SRT/JSON and is never mutated by
    the enhancer.
    """

    raw = (
        render_chaptered_markdown(
            transcript,
            chapters,
            window_seconds=settings.transcript_window_seconds,
        )
        if chapters
        else render_markdown(
            transcript,
            window_seconds=settings.transcript_window_seconds,
        )
    )
    return enhance_markdown(raw, settings)
