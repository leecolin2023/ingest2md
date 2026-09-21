"""Long-lived execution resources shared by single and batch ingestion."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ingest2md.browser import BrowserRuntime
from ingest2md.config import Settings
from ingest2md.transcription.service import ASRBackend, create_asr_backend


@dataclass
class RuntimeContext:
    """Execution resources only; batch task state intentionally lives elsewhere."""

    settings: Settings
    output_dir: Path
    _asr_backend: ASRBackend | None = field(default=None, init=False, repr=False)
    _browser: BrowserRuntime | None = field(default=None, init=False, repr=False)

    def get_asr_backend(self) -> ASRBackend:
        if self._asr_backend is None:
            self._asr_backend = create_asr_backend(self.settings)
        return self._asr_backend

    @property
    def browser(self) -> BrowserRuntime:
        if self._browser is None:
            self._browser = BrowserRuntime()
        return self._browser

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()

    async def __aenter__(self) -> "RuntimeContext":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
