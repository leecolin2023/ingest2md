"""Shared ffmpeg helpers; each ASR backend chooses its own chunk format and size."""
import os
import subprocess
from pathlib import Path


def _ffmpeg_bin(name: str) -> str:
    """Prefer PATH; fall back to the common Windows winget FFmpeg location."""
    from shutil import which

    path = which(name)
    if path:
        return path
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for pkg in winget.glob("Gyan.FFmpeg*/ffmpeg-*/bin"):
        if (pkg / f"{name}.exe").exists():
            return str(pkg / f"{name}.exe")
    raise FileNotFoundError(f"找不到 {name}，请安装 ffmpeg 后重试")


def probe_duration(audio_path: str) -> float:
    out = subprocess.run(
        [_ffmpeg_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _chunk_audio(audio_path: str, chunk_seconds: int, limit_seconds: int,
                 out_dir: str | Path, *, extension: str, codec_args: list[str]) -> list[dict]:
    """Split media with one ffmpeg process instead of spawning once per chunk."""
    if chunk_seconds <= 0 or limit_seconds < 0:
        raise ValueError("切段时长必须大于零，处理时长不能为负数")
    src = Path(audio_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_total = probe_duration(str(src))
    limited = bool(limit_seconds and limit_seconds < source_total)
    total = float(limit_seconds) if limited else source_total
    if total <= 0.5:
        return []

    # Temporary work directories are normally empty, but clearing matching stale
    # files makes retries deterministic when callers intentionally reuse one.
    for stale in out_dir.glob(f"chunk_*.{extension}"):
        try:
            stale.unlink()
        except OSError:
            pass

    target_pattern = out_dir / f"chunk_%04d.{extension}"
    cmd = [
        _ffmpeg_bin("ffmpeg"), "-y", "-v", "error",
        "-i", str(src), "-vn",
    ]
    if limited:
        cmd.extend(["-t", str(total)])
    cmd.extend([
        *codec_args,
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-reset_timestamps", "1",
        str(target_pattern),
    ])
    subprocess.run(cmd, check=True, capture_output=True)

    files = sorted(out_dir.glob(f"chunk_*.{extension}"))
    chunks: list[dict] = []
    for index, target in enumerate(files):
        start = index * chunk_seconds
        if start >= total - 0.5:
            break
        end = min(start + chunk_seconds, total)
        chunks.append({
            "path": str(target),
            "start": round(float(start), 3),
            "end": round(float(end), 3),
        })
    return chunks


def chunk_audio_mp3(audio_path: str, chunk_seconds: int, limit_seconds: int,
                    out_dir: str | Path) -> list[dict]:
    """64kbps 16kHz mono MP3 for cloud / multimodal LLM upload."""
    return _chunk_audio(
        audio_path, chunk_seconds, limit_seconds, out_dir,
        extension="mp3",
        codec_args=["-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-b:a", "64k"],
    )


def chunk_audio_wav(audio_path: str, chunk_seconds: int, limit_seconds: int,
                    out_dir: str | Path) -> list[dict]:
    """16kHz mono PCM WAV for SenseVoice ONNX."""
    return _chunk_audio(
        audio_path, chunk_seconds, limit_seconds, out_dir,
        extension="wav",
        codec_args=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"],
    )


# Backward-compatible helper for callers from v0.7; new backends call the
# explicit format-specific helpers above.
def chunk_audio(audio_path: str, chunk_seconds: int, limit_seconds: int = 0,
                out_dir: str | None = None) -> list[dict]:
    src = Path(audio_path)
    target = Path(out_dir) if out_dir else src.parent / "chunks"
    return chunk_audio_mp3(audio_path, chunk_seconds, limit_seconds, target)


def cleanup_chunks(chunks: list[dict]) -> None:
    for chunk in chunks:
        try:
            os.remove(chunk["path"])
        except OSError:
            pass
