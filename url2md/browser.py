"""Browser helpers for sites that need a real browser session."""
from __future__ import annotations

from pathlib import Path


def load_netscape_cookies(path: str, domain_contains: str = "") -> list[dict]:
    """Parse a Netscape cookie file into Playwright cookie dictionaries.

    The helper intentionally accepts the common yt-dlp/browser export format so
    users do not need another cookie format just for web extractors.
    """
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
        domain, _include_sub, cookie_path, secure, expires, name, value = parts[:7]
        if domain_contains and domain_contains not in domain:
            continue
        item = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": cookie_path or "/",
            "secure": secure.upper() == "TRUE",
            "httpOnly": http_only,
        }
        try:
            expiry = int(expires)
            if expiry > 0:
                item["expires"] = expiry
        except ValueError:
            pass
        cookies.append(item)
    return cookies


async def launch_chromium(playwright, headless: bool = True):
    """Launch Chromium, preferring an already-installed full browser binary.

    Some environments have Playwright's full Chromium but not the separate
    headless-shell package. Explicit executable_path keeps the CLI usable there.
    """
    from shutil import which
    executable = Path(playwright.chromium.executable_path)
    kwargs = {"headless": headless}
    if executable.is_file():
        kwargs["executable_path"] = str(executable)
    else:
        system_browser = which("chromium") or which("chromium-browser") or which("google-chrome") or which("google-chrome-stable")
        if system_browser:
            kwargs["executable_path"] = system_browser
    return await playwright.chromium.launch(**kwargs)
