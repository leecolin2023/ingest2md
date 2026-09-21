from __future__ import annotations

import asyncio
from pathlib import Path

from ingest2md.batch.models import BatchItem, config_fingerprint
from ingest2md.batch.runner import BatchRunner
from ingest2md.batch.store import TaskStore
from ingest2md.cache import MediaCache
from ingest2md.config import Settings
from ingest2md.engine import IngestionResult
from ingest2md.model import Document, write_document
from ingest2md.transcription.model import Segment, TranscriptResult
from ingest2md.transcription.presentation import present_transcript


def test_v011_same_title_different_web_sources_do_not_overwrite(tmp_path: Path):
    first = Document(
        title="AI行业报告",
        source_url="https://example.com/a",
        source_type="web",
        body_md="A",
    )
    second = Document(
        title="AI行业报告",
        source_url="https://example.com/b",
        source_type="web",
        body_md="B",
    )
    first_path = write_document(first, tmp_path)
    second_path = write_document(second, tmp_path)

    assert first_path != second_path
    assert first_path.exists()
    assert second_path.exists()
    assert first_path.read_text(encoding="utf-8").endswith("A\n")
    assert second_path.read_text(encoding="utf-8").endswith("B\n")


def test_v011_ingestion_name_and_tags_are_user_metadata():
    doc = Document(
        title="原始标题",
        source_url="https://example.com",
        source_type="web",
        ingestion_name="Agent案例",
        ingestion_tags=("AI", "Agent"),
        body_md="正文",
    )
    markdown = doc.build_markdown()
    assert markdown.startswith("# 原始标题")
    assert "> **任务名称**: Agent案例" in markdown
    assert "> **标签**: AI, Agent" in markdown


def test_v011_task_store_upserts_batch_metadata(tmp_path: Path):
    store = TaskStore(tmp_path / "state.sqlite3")
    settings = Settings(output_dir=str(tmp_path))
    fingerprint = config_fingerprint(settings)
    try:
        ids = store.register(
            [BatchItem("https://example.com/a", name="旧名称", tags=("old",))],
            fingerprint,
        )
        store.register(
            [BatchItem("https://example.com/a", name="新名称", tags=("new", "ai"))],
            fingerprint,
        )
        row = store.db.execute("SELECT * FROM tasks WHERE id=?", (ids[0],)).fetchone()
        assert row["name"] == "新名称"
        assert '"new"' in row["tags_json"]
        assert '"ai"' in row["tags_json"]
    finally:
        store.close()


def test_v011_metadata_change_reopens_successful_task(tmp_path: Path):
    store = TaskStore(tmp_path / "state.sqlite3")
    settings = Settings(output_dir=str(tmp_path))
    fingerprint = config_fingerprint(settings)
    output = tmp_path / "one.md"
    output.write_text("one", encoding="utf-8")
    try:
        task_id = store.register(
            [BatchItem("https://example.com/a", name="旧名称", tags=("old",))],
            fingerprint,
        )[0]
        result = IngestionResult(
            "https://example.com/a", "https://example.com/a", "Fake",
            "web", "1", "one", output, "web:1",
            Document(
                title="one", source_url="https://example.com/a",
                source_type="web", source_id="1", body_md="one",
            ),
        )
        store.mark_success(task_id, result)

        store.register(
            [BatchItem("https://example.com/a", name="新名称", tags=("new",))],
            fingerprint,
        )
        row = store.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        assert row["status"] == "pending"
        assert row["name"] == "新名称"
        assert '"new"' in row["tags_json"]
    finally:
        store.close()


def test_v011_canonical_identity_finds_completed_duplicate(tmp_path: Path):
    store = TaskStore(tmp_path / "state.sqlite3")
    settings = Settings(output_dir=str(tmp_path))
    fingerprint = config_fingerprint(settings)
    output = tmp_path / "one.md"
    output.write_text("one", encoding="utf-8")
    try:
        first, second = store.register(
            [
                BatchItem("https://short.example/a"),
                BatchItem("https://canonical.example/video/42"),
            ],
            fingerprint,
        )
        result = IngestionResult(
            "https://short.example/a",
            "https://short.example/a",
            "Fake",
            "video",
            "42",
            "one",
            output,
            "video:42",
            Document(
                title="one",
                source_url="https://canonical.example/video/42",
                source_type="video",
                source_id="42",
                body_md="one",
            ),
        )
        store.mark_success(first, result)
        store.set_identity(second, "video:42", "video", "42")
        duplicate = store.find_completed_by_canonical(
            "video:42", fingerprint, exclude_task_id=second
        )
        assert duplicate is not None
        store.mark_duplicate(second, duplicate)
        summary = store.summary([first, second])
        assert summary.success == 1
        assert summary.duplicate == 1
    finally:
        store.close()


def test_v011_batch_runner_retries_transient_failure(tmp_path: Path, monkeypatch):
    calls = {"count": 0}

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("ingest2md.batch.runner.asyncio.sleep", no_sleep)

    class FakeEngine:
        settings = Settings(output_dir=str(tmp_path), batch_retry_attempts=3)

        async def ingest_one(self, request):
            calls["count"] += 1
            if calls["count"] < 3:
                raise TimeoutError("temporary timeout")
            path = tmp_path / "ok.md"
            path.write_text("ok", encoding="utf-8")
            doc = Document(
                title="ok",
                source_url=request.source,
                source_type="web",
                source_id="1",
                body_md="ok",
            )
            return IngestionResult(
                request.source, request.source, "Fake", "web", "1", "ok",
                path, "web:1", doc,
            )

    store = TaskStore(tmp_path / "state.sqlite3")
    try:
        summary = asyncio.run(
            BatchRunner(FakeEngine(), store).run(
                [BatchItem("https://example.com/retry")]
            )
        )
        assert calls["count"] == 3
        assert summary.success == 1
        assert summary.failed == 0
    finally:
        store.close()


def test_v011_presentation_enhancer_does_not_mutate_raw_transcript(monkeypatch):
    transcript = TranscriptResult(
        segments=[Segment(0, 30, "原始 asr 文本")],
        models=["fake-asr"],
        processed_seconds=30,
    )
    settings = Settings(
        transcript_enhance="llm",
        llm_api_key="fake",
        llm_model="fake-model",
    )

    def fake_enhance(self, text):
        return text.replace("asr", "ASR")

    monkeypatch.setattr(
        "ingest2md.transcription.enhancer.TranscriptEnhancer.enhance_text",
        fake_enhance,
    )
    markdown = present_transcript(transcript, settings)

    assert "原始 ASR 文本" in markdown
    assert transcript.segments[0].text == "原始 asr 文本"
    assert markdown.startswith("### 00:00–00:30")


def test_v011_media_cache_roundtrip(tmp_path: Path):
    cache = MediaCache(tmp_path / "cache")
    source = tmp_path / "audio.mp3"
    source.write_bytes(b"audio")

    stored = cache.store("youtube:abcdefghijk", source)
    assert stored.exists()
    assert cache.get("youtube:abcdefghijk") == stored

    cache.discard("youtube:abcdefghijk")
    assert cache.get("youtube:abcdefghijk") is None


def test_v011_batch_status_report_includes_duplicates_and_errors(tmp_path: Path):
    store = TaskStore(tmp_path / "state.sqlite3")
    settings = Settings(output_dir=str(tmp_path))
    fingerprint = config_fingerprint(settings)
    try:
        ids = store.register(
            [BatchItem("https://example.com/a"), BatchItem("https://example.com/b")],
            fingerprint,
        )
        store.mark_failed(ids[0], "timeout", "temporary", retryable=True)
        report = store.status_report()
        assert report["total"] == 2
        assert report["counts"]["failed"] == 1
        assert report["counts"]["pending"] == 1
        assert report["errors"]["timeout"] == 1
    finally:
        store.close()
