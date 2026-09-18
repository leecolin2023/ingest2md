"""Convert source subtitles into the shared TranscriptResult contract."""
from __future__ import annotations

import logging

from ingest2md.config import Settings
from ingest2md.media.subtitles import SubtitleTrack
from ingest2md.transcription.model import Segment, TranscriptResult
from ingest2md.transcription.translation import Translator, make_translator, translate_text

logger = logging.getLogger(__name__)


def subtitles_to_transcript(track: SubtitleTrack, settings: Settings,
                            translator: Translator | None = None) -> TranscriptResult:
    """Group subtitle cues into bounded windows, then translate each window."""
    cues = track.cues
    if settings.limit_seconds:
        cues = [cue for cue in cues if cue.start < settings.limit_seconds]
    if not cues:
        raise ValueError("字幕为空或超出 --limit-seconds 范围")

    translator = translator or make_translator(settings)
    windows: list[tuple[float, float, str]] = []
    start = cues[0].start
    end = cues[0].end
    texts: list[str] = []
    window_limit = start + settings.chunk_seconds

    for cue in cues:
        if texts and cue.start >= window_limit:
            windows.append((start, end, " ".join(texts)))
            start = cue.start
            end = cue.end
            texts = []
            window_limit = start + settings.chunk_seconds
        texts.append(cue.text)
        end = max(end, cue.end)
    if texts:
        windows.append((start, end, " ".join(texts)))

    segments: list[Segment] = []
    for index, (start, end, original) in enumerate(windows, 1):
        logger.info("中文字幕处理 [%s/%s]", index, len(windows))
        translated = translate_text(original, translator)
        segments.append(Segment(start, end, translated, original))

    model_label = f"{track.kind}-subtitle:{track.language}"
    return TranscriptResult(
        segments=segments,
        models=[model_label],
        processed_seconds=min(windows[-1][1], settings.limit_seconds or windows[-1][1]),
        timestamp_precision="subtitle-window",
        translation_models=list(getattr(translator, "used_models", [])),
    )
