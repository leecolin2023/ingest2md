"""Convert source subtitles directly into the shared transcript contract."""
from __future__ import annotations

from ingest2md.config import Settings
from ingest2md.media.subtitles import SubtitleTrack
from ingest2md.transcription.model import Segment, TranscriptResult


def subtitles_to_transcript(track: SubtitleTrack, settings: Settings) -> TranscriptResult:
    """Group subtitle cues into readable windows without translating them."""
    cues = track.cues
    if settings.limit_seconds:
        cues = [cue for cue in cues if cue.start < settings.limit_seconds]
    if not cues:
        raise ValueError("字幕为空或超出 --limit-seconds 范围")

    windows: list[tuple[float, float, str]] = []
    start = cues[0].start
    end = cues[0].end
    texts: list[str] = []
    window_limit = start + settings.subtitle_window_seconds

    for cue in cues:
        if texts and cue.start >= window_limit:
            windows.append((start, end, " ".join(texts)))
            start = cue.start
            end = cue.end
            texts = []
            window_limit = start + settings.subtitle_window_seconds
        texts.append(cue.text)
        end = max(end, cue.end)
    if texts:
        windows.append((start, end, " ".join(texts)))

    return TranscriptResult(
        segments=[Segment(start, end, text) for start, end, text in windows],
        models=[f"{track.kind}-subtitle:{track.language}"],
        processed_seconds=min(windows[-1][1], settings.limit_seconds or windows[-1][1]),
        timestamp_precision="subtitle-window",
        language=track.language,
    )
