"""Long-lived resources shared by single/batch ingestion executions."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ingest2md.browser import BrowserRuntime
from ingest2md.config import Settings
from ingest2md.transcription.service import ASRBackend, create_asr_backend


@dataclass
class RuntimeContext:
    """Execution resources, deliberately separate from batch task state."""

    settings: Settings
    output_dir: Path | None = None
    _asr_backend: ASRBackend | None = field(default=None, init=False, repr=False)
    _browser: BrowserRuntime | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if self.output_dir is None:
            self.output_dir = Path(self.settings.output_dir).expanduser().resolve()
        else:
            self.output_dir = Path(self.output_dir).expanduser().resolve()

    @property
    def asr_backend(self) -> ASRBackend:
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

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
