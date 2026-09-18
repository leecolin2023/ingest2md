"""Small HTTP streaming downloader for public media URLs."""
from __future__ import annotations

from pathlib import Path

import httpx

from ingest2md.netutils import DEFAULTDEFAULT_USER_AGENT


def download_url(url: str, target: Path, *, max_bytes: int = 750 * 1024 * 1024) -> Path:
    """Stream one public media file to ``target`` with a conservative size cap."""
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with httpx.Client(
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"},
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=120.0),
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > max_bytes:
                    raise ValueError(f"媒体文件过大（>{max_bytes // 1024 // 1024} MB）")
                with target.open("wb") as stream:
                    for chunk in response.iter_bytes(1024 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            raise ValueError(f"媒体文件过大（>{max_bytes // 1024 // 1024} MB）")
                        stream.write(chunk)
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    if written == 0:
        target.unlink(missing_ok=True)
        raise ValueError("下载到的媒体文件为空")
    return target
