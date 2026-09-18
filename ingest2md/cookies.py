"""Shared Netscape cookies.txt parsing."""
from __future__ import annotations

from pathlib import Path


def parse_netscape_cookie_file(path: str) -> list[dict]:
    """Parse Mozilla/Netscape cookies.txt into normalized dictionaries."""
    if not path:
        return []
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"Cookie 文件不存在: {file}")

    cookies: list[dict] = []
    for raw in file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        http_only = False
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
            http_only = True
        elif not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, include_subdomains, cookie_path, secure, expires, name, value = parts[:7]
        try:
            expiry = int(expires)
        except ValueError:
            expiry = 0
        cookies.append({
            "domain": domain,
            "include_subdomains": include_subdomains.upper() == "TRUE",
            "path": cookie_path or "/",
            "secure": secure.upper() == "TRUE",
            "expires": expiry,
            "name": name,
            "value": value,
            "http_only": http_only,
        })
    return cookies
