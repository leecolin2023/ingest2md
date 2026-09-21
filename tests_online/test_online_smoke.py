"""Manual online smoke corpus.

This directory is intentionally excluded from the default pytest testpaths.
Set only the sources you want to verify, then run:

    python -m pytest tests_online -q

Use INGEST2MD_ONLINE_CONFIG when a source needs cookies/cloud configuration.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from ingest2md.config import load_settings
from ingest2md.engine import IngestionEngine, IngestionRequest
from ingest2md.runtime import RuntimeContext


_CASES = [
    ("generic_web", "INGEST2MD_SMOKE_WEB"),
    ("youtube", "INGEST2MD_SMOKE_YOUTUBE"),
    ("bilibili", "INGEST2MD_SMOKE_BILIBILI"),
    ("xiaoyuzhou", "INGEST2MD_SMOKE_XIAOYUZHOU"),
    ("douyin", "INGEST2MD_SMOKE_DOUYIN"),
]


@pytest.mark.parametrize("case_name,env_name", _CASES)
def test_online_source(case_name: str, env_name: str, tmp_path: Path):
    source = os.environ.get(env_name, "").strip()
    if not source:
        pytest.skip(f"{env_name} 未设置")

    config_path = os.environ.get("INGEST2MD_ONLINE_CONFIG") or None
    settings = load_settings(
        config_path,
        output_dir=str(tmp_path / case_name),
    )

    async def run():
        async with RuntimeContext(settings) as runtime:
            engine = IngestionEngine(settings, runtime=runtime)
            return await engine.ingest_one(IngestionRequest(source))

    result = asyncio.run(run())
    assert result.output_path.is_file()
    assert result.document.title.strip()
    assert result.document.body_md.strip()
