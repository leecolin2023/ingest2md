"""Render structured transcripts without leaking ASR chunk size into presentation."""
from __future__ import annotations

from ingest2md.transcription.model import Segment, TranscriptResult


def srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def short_time(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def group_segments(
    segments: list[Segment],
    window_seconds: int = 300,
    total_seconds: float = 0,
) -> list[dict]:
    """Group low-level transcript segments into readable presentation windows."""
    if window_seconds <= 0:
        raise ValueError("window_seconds 必须是正整数")

    usable = [segment for segment in segments if segment.text.strip()]
    if not usable:
        return []

    total = max(
        float(total_seconds or 0),
        max(float(segment.end) for segment in usable),
    )
    grouped: list[dict] = []
    current_key = None
    current: dict | None = None

    for segment in usable:
        key = int(max(0.0, float(segment.start)) // window_seconds)
        if key != current_key:
            if current is not None:
                grouped.append(current)
            start = float(key * window_seconds)
            current = {
                "start": start,
                "end": min(start + window_seconds, total),
                "texts": [],
            }
            current_key = key
        current["end"] = min(
            total,
            max(float(current["end"]), float(segment.end)),
        )
        current["texts"].append(segment.text.strip())

    if current is not None:
        grouped.append(current)

    for item in grouped:
        item["text"] = "\n\n".join(item.pop("texts"))
    return grouped


def render_markdown(transcript: TranscriptResult, window_seconds: int = 300) -> str:
    """Render readable time windows while keeping raw ASR segments untouched."""
    return "\n\n".join(
        f"### {short_time(group['start'])}–{short_time(group['end'])}\n\n{group['text']}"
        for group in group_segments(
            transcript.segments,
            window_seconds=window_seconds,
            total_seconds=transcript.processed_seconds,
        )
    )


def render_chaptered_markdown(
    transcript: TranscriptResult,
    chapters: list[tuple[float, str]],
    window_seconds: int = 300,
) -> str:
    """Render semantic chapters while using presentation windows only for paragraphs."""
    total = max(
        float(transcript.processed_seconds or 0),
        max((float(segment.end) for segment in transcript.segments), default=0.0),
    )
    cleaned: list[tuple[float, str]] = []
    seen_starts: set[float] = set()
    for start, title in sorted(chapters, key=lambda item: item[0]):
        start = max(0.0, float(start))
        title = str(title or "").strip()
        if not title or start >= total or start in seen_starts:
            continue
        seen_starts.add(start)
        cleaned.append((start, title))

    if not cleaned:
        return render_markdown(transcript, window_seconds=window_seconds)
    if cleaned[0][0] > 1.0:
        cleaned.insert(0, (0.0, "开场"))

    rendered: list[str] = []
    for index, (start, title) in enumerate(cleaned):
        end = cleaned[index + 1][0] if index + 1 < len(cleaned) else total
        selected = [
            segment for segment in transcript.segments
            if segment.text.strip()
            and start <= ((float(segment.start) + float(segment.end)) / 2) < end
        ]
        if not selected:
            continue
        paragraphs = group_segments(
            selected,
            window_seconds=window_seconds,
            total_seconds=end,
        )
        body = "\n\n".join(group["text"] for group in paragraphs if group["text"])
        if body:
            rendered.append(f"### {short_time(start)} {title}\n\n{body}")

    return "\n\n".join(rendered) or render_markdown(
        transcript,
        window_seconds=window_seconds,
    )


def render_srt(transcript: TranscriptResult) -> str:
    return "".join(
        f"{i}\n{srt_time(s.start)} --> {srt_time(s.end)}\n{s.text}\n\n"
        for i, s in enumerate(transcript.segments, 1)
    )
