"""Browser helpers for sites that need a real browser session."""
from __future__ import annotations

from contextlib import asynccontextmanager
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
    """Launch Chromium, preferring an already-installed full browser binary."""
    from shutil import which

    executable = Path(playwright.chromium.executable_path)
    kwargs = {"headless": headless}
    if executable.is_file():
        kwargs["executable_path"] = str(executable)
    else:
        system_browser = (
            which("chromium") or which("chromium-browser")
            or which("google-chrome") or which("google-chrome-stable")
        )
        if system_browser:
            kwargs["executable_path"] = system_browser
    return await playwright.chromium.launch(**kwargs)


class BrowserRuntime:
    """One lazily started Playwright/Chromium process shared across tasks.

    BrowserContext objects are still created per task and always closed after
    use, so cookies/session state do not leak between adapters.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None

    async def start(self):
        if self._browser is not None:
            return self._browser
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await launch_chromium(self._playwright, headless=self.headless)
        return self._browser

    async def new_context(self, **kwargs):
        browser = await self.start()
        return await browser.new_context(**kwargs)

    async def close(self) -> None:
        browser, playwright = self._browser, self._playwright
        self._browser = None
        self._playwright = None
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()


@asynccontextmanager
async def browser_context(runtime: BrowserRuntime | None = None, **kwargs):
    """Create an isolated BrowserContext, optionally on a shared Chromium."""
    if runtime is not None:
        context = await runtime.new_context(**kwargs)
        try:
            yield context
        finally:
            await context.close()
        return

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await launch_chromium(playwright, headless=True)
        context = await browser.new_context(**kwargs)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()
