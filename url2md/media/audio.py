"""音频切分：用 ffmpeg 把音频切成适合 API 单次请求的段落。"""

import os
import subprocess
from pathlib import Path


def _ffmpeg_bin(name: str) -> str:
    """优先用 PATH 中的 ffmpeg；否则回退到 winget 安装位置。"""
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


def chunk_audio(audio_path: str, chunk_seconds: int, limit_seconds: int = 0,
                out_dir: str = None) -> list:
    """把音频转码为 16kHz 单声道 mp3 并切段。

    返回 [{path, start, end}]，start/end 为相对原音频的秒数。
    """
    if chunk_seconds <= 0 or limit_seconds < 0:
        raise ValueError("切段时长必须大于零，处理时长不能为负数")
    src = Path(audio_path)
    out_dir = Path(out_dir) if out_dir else src.parent / "chunks"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = probe_duration(audio_path)
    if limit_seconds and limit_seconds < total:
        total = limit_seconds

    chunks = []
    idx = 0
    start = 0.0
    while start < total - 0.5:
        end = min(start + chunk_seconds, total)
        seg = out_dir / f"chunk_{idx:03d}.mp3"
        cmd = [
            _ffmpeg_bin("ffmpeg"), "-y", "-v", "error",
            "-ss", str(start), "-to", str(end), "-i", str(src),
            "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-b:a", "64k",
            str(seg),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        chunks.append({"path": str(seg), "start": round(start, 2), "end": round(end, 2)})
        idx += 1
        start = end
    return chunks


def cleanup_chunks(chunks: list):
    for c in chunks:
        try:
            os.remove(c["path"])
        except OSError:
            pass
