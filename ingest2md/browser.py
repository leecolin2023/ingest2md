"""Browser helpers for sites that need a real browser session."""
from __future__ import annotations

from pathlib import Path

from ingest2md.cookies import parse_netscape_cookie_file


def load_netscape_cookies(path: str, domain_contains: str = "") -> list[dict]:
    """Convert shared Netscape cookie records to Playwright dictionaries."""
    cookies: list[dict] = []
    for record in parse_netscape_cookie_file(path):
        domain = record["domain"]
        if domain_contains and domain_contains.lower() not in domain.lower():
            continue
        item = {
            "name": record["name"],
            "value": record["value"],
            "domain": domain,
            "path": record["path"],
            "secure": record["secure"],
            "httpOnly": record["http_only"],
        }
        if record["expires"] > 0:
            item["expires"] = record["expires"]
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
