"""Integration coverage: real IngestionEngine -> write_document -> source index."""
import asyncio
import logging
from pathlib import Path

from ingest2md.config import Settings
from ingest2md.engine import IngestionEngine, IngestionRequest
from ingest2md.model import Document


class FakeExtractor:
    name = "stub"

    async def extract(self, reference: str, output_dir: Path) -> Document:
        return Document(
            title="Demo", source_url=reference, source_type="web",
            source_id="123", body_md="Hello",
        )


def test_ingestion_engine_creates_and_deduplicates_index(tmp_path: Path, monkeypatch):
    import ingest2md.engine as engine

    monkeypatch.setattr(engine, "find_extractor", lambda reference, **kwargs: FakeExtractor())
    client = IngestionEngine(Settings(output_dir=str(tmp_path)))
    url = "https://example.com/hello"
    result = asyncio.run(client.ingest_one(IngestionRequest(url)))

    assert result.output_path.exists()
    assert result.canonical_key == "web:123"
    assert "Hello" in result.output_path.read_text(encoding="utf-8")
    index = tmp_path / "sources.md"
    assert index.is_file()
    assert f"| {url} | FakeExtractor | `{result.output_path.name}` |" in index.read_text(encoding="utf-8")

    asyncio.run(client.ingest_one(url))
    assert index.read_text(encoding="utf-8").count(f"| {url} |") == 1


def test_ingestion_preserves_product_when_index_write_fails(tmp_path: Path, monkeypatch, caplog):
    import ingest2md.engine as engine

    monkeypatch.setattr(engine, "find_extractor", lambda reference, **kwargs: FakeExtractor())

    def fail(*args, **kwargs):
        raise OSError("index disk unavailable")

    monkeypatch.setattr(engine, "record_source", fail)
    client = IngestionEngine(Settings(output_dir=str(tmp_path)))
    with caplog.at_level(logging.WARNING):
        result = asyncio.run(client.ingest_one("https://example.com/hello"))
    assert result.output_path.is_file()
    assert "index disk unavailable" in caplog.text


def test_reserved_sources_title_does_not_overwrite_index(tmp_path: Path, monkeypatch):
    import ingest2md.engine as engine

    class ReservedNameExtractor:
        name = "reserved"

        async def extract(self, reference, output_dir):
            return Document(title="sources", source_url=reference, body_md="real content")

    monkeypatch.setattr(
        engine, "find_extractor", lambda reference, **kwargs: ReservedNameExtractor(),
    )
    client = IngestionEngine(Settings(output_dir=str(tmp_path)))
    result = asyncio.run(client.ingest_one("https://example.com/reserved"))
    assert result.output_path.name.endswith("__sources.md")
    assert result.output_path.name != "sources.md"
    assert "real content" in result.output_path.read_text(encoding="utf-8")
    index_text = (tmp_path / "sources.md").read_text(encoding="utf-8")
    assert index_text.startswith("# 转写链接记录")
    assert result.output_path.name in index_text

    second = asyncio.run(client.ingest_one("https://example.com/reserved"))
    assert second.output_path == result.output_path
    assert index_text == (tmp_path / "sources.md").read_text(encoding="utf-8")
