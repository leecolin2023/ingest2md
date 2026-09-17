"""Render structured transcripts."""
from url2md.transcription.model import TranscriptResult


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


def render_markdown(transcript: TranscriptResult) -> str:
    return "\n\n".join(
        f"### {short_time(s.start)}–{short_time(s.end)}\n\n{s.text.strip()}"
        for s in transcript.segments
        if s.text.strip()
    )


def render_srt(transcript: TranscriptResult) -> str:
    return "".join(
        f"{i}\n{srt_time(s.start)} --> {srt_time(s.end)}\n{s.text}\n\n"
        for i, s in enumerate(transcript.segments, 1)
    )
