"""Regression tests for dated, length-bounded output names and safe replacement."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from ingest2md.config import Settings
from ingest2md.engine import IngestionEngine
from ingest2md.model import Document, write_document


CST = timezone(timedelta(hours=8))


def _time(day: int) -> datetime:
    return datetime(2026, 10, day, 8, 54, 30, tzinfo=CST)


def test_filename_only_has_date_and_title(tmp_path):
    doc = Document("视频标题", "https://example.com/1", source_id="BV123", captured_at=_time(22))
    path = write_document(doc, tmp_path)
    assert path.name == "20261022__视频标题.md"
    assert "BV123" not in path.name
    assert "085430" not in path.name
    assert doc.dirname == "20261022__视频标题"
    assert "# 视频标题" in path.read_text(encoding="utf-8")


def test_date_uses_china_timezone_not_utc_day():
    doc = Document("跨日", "https://example.com", captured_at=datetime(
        2026, 10, 21, 20, tzinfo=timezone.utc
    ))
    assert doc.dirname == "20261022__跨日"


def test_150_utf8_byte_budget_does_not_split_characters(tmp_path):
    doc = Document("中文🙂" * 200, "https://example.com/long", captured_at=_time(22))
    path = write_document(doc, tmp_path)
    assert len(path.name.encode("utf-8")) <= 150
    assert path.name.startswith("20261022__")
    assert path.suffix == ".md"
    assert "�" not in path.name
    assert doc.title in path.read_text(encoding="utf-8")


def test_grouped_markdown_uses_fixed_content_filename(tmp_path):
    doc = Document("含图文章", "https://example.com", captured_at=_time(22),
                   image_map={"https://example.com/a": "images/01.jpg"})
    images = tmp_path / doc.dirname / "images"
    images.mkdir(parents=True)
    (images / "01.jpg").write_bytes(b"image")
    path = write_document(doc, tmp_path, formats=("json", "txt"))
    assert path == tmp_path / "20261022__含图文章" / "content.md"
    assert (path.parent / "document.json").is_file()
    assert (path.parent / "transcript.txt").is_file()
    assert (path.parent / "images" / "01.jpg").read_bytes() == b"image"
    assert len(path.parent.name.encode("utf-8")) <= 150


def _mock_engine(tmp_path, monkeypatch, titles, dates, grouped=False, fail_on=None):
    import ingest2md.engine as engine

    state = {"n": 0}

    class FakeExtractor:
        name = "test-source"

        async def extract(self, reference, staging_dir):
            index = state["n"]
            state["n"] += 1
            doc = Document(
                title=titles[index], source_url=reference, source_type="fake",
                source_id=str(index), captured_at=dates[index],
                body_md=f"version-{index}",
            )
            if grouped:
                image_dir = staging_dir / doc.dirname / "images"
                image_dir.mkdir(parents=True)
                (image_dir / "image.jpg").write_bytes(f"version-{index}".encode())
                doc.image_map = {"https://example.com/i.jpg": "images/image.jpg"}
            if fail_on == index:
                raise RuntimeError("simulated extraction failure")
            return doc

    monkeypatch.setattr(engine, "find_extractor", lambda reference, **kw: FakeExtractor())
    return IngestionEngine(Settings(output_dir=str(tmp_path)))


def _primary_outputs(root):
    return sorted(p for p in root.iterdir()
                  if p.name.startswith(("20261021__", "20261022__", "20261023__")))


def test_same_title_same_day_overwrites_not_duplicates(tmp_path, monkeypatch):
    engine = _mock_engine(tmp_path, monkeypatch, ["相同标题", "相同标题"],
                          [_time(22), _time(22)])
    first = asyncio.run(engine.ingest_one("https://example.com/one"))
    second = asyncio.run(engine.ingest_one("https://example.com/one"))
    assert first.output_path == second.output_path
    assert len(_primary_outputs(tmp_path)) == 1
    assert "version-1" in second.output_path.read_text(encoding="utf-8")
    assert "version-0" not in second.output_path.read_text(encoding="utf-8")


def test_same_title_different_day_replaces_previous_file(tmp_path, monkeypatch):
    engine = _mock_engine(tmp_path, monkeypatch, ["跨日标题", "跨日标题"],
                          [_time(21), _time(22)])
    old = asyncio.run(engine.ingest_one("https://example.com/same"))
    new = asyncio.run(engine.ingest_one("https://example.com/same"))
    assert not old.output_path.exists()
    assert new.output_path.name == "20261022__跨日标题.md"
    assert len(_primary_outputs(tmp_path)) == 1
    index = (tmp_path / "sources.md").read_text(encoding="utf-8")
    assert "20261022__跨日标题.md" in index
    assert "20261021__跨日标题.md" not in index
    assert "2026-10-22" in index


def test_grouped_reingestion_replaces_assets_not_only_content(tmp_path, monkeypatch):
    engine = _mock_engine(tmp_path, monkeypatch, ["含图标题", "含图标题"],
                          [_time(21), _time(22)], grouped=True)
    first = asyncio.run(engine.ingest_one("https://example.com/same"))
    assert first.output_path.name == "content.md"
    assert first.output_path.parent.name == "20261021__含图标题"
    old_dir = first.output_path.parent
    (old_dir / "stale.txt").write_text("old", encoding="utf-8")
    second = asyncio.run(engine.ingest_one("https://example.com/same"))
    assert not old_dir.exists()
    assert second.output_path == tmp_path / "20261022__含图标题" / "content.md"
    assert not (second.output_path.parent / "stale.txt").exists()
    assert (second.output_path.parent / "images" / "image.jpg").read_bytes() == b"version-1"


def test_extraction_failure_does_not_remove_previous_output(tmp_path, monkeypatch):
    engine = _mock_engine(tmp_path, monkeypatch, ["同标题", "同标题"],
                          [_time(21), _time(22)], grouped=True, fail_on=1)
    old = asyncio.run(engine.ingest_one("https://example.com/same"))
    with pytest.raises(RuntimeError, match="simulated extraction failure"):
        asyncio.run(engine.ingest_one("https://example.com/same"))
    assert old.output_path.is_file()
    assert "version-0" in old.output_path.read_text(encoding="utf-8")
    assert len(_primary_outputs(tmp_path)) == 1
    assert not list(tmp_path.glob(".ingest2md-stage-*"))


def test_distinct_full_titles_that_truncate_to_same_name_do_not_overwrite(tmp_path, monkeypatch):
    prefix = "长" * 80
    engine = _mock_engine(tmp_path, monkeypatch, [prefix + "甲", prefix + "乙"],
                          [_time(22), _time(22)])
    old = asyncio.run(engine.ingest_one("https://example.com/a"))
    with pytest.raises(FileExistsError, match="截断"):
        asyncio.run(engine.ingest_one("https://example.com/b"))
    assert old.output_path.is_file()
    assert prefix + "甲" in old.output_path.read_text(encoding="utf-8")
    assert len(_primary_outputs(tmp_path)) == 1


def test_cross_day_unrelated_truncated_titles_are_not_deleted(tmp_path, monkeypatch):
    prefix = "长" * 80
    engine = _mock_engine(tmp_path, monkeypatch, [prefix + "甲", prefix + "乙"],
                          [_time(21), _time(22)])
    first = asyncio.run(engine.ingest_one("https://example.com/a"))
    second = asyncio.run(engine.ingest_one("https://example.com/b"))
    assert first.output_path.is_file()
    assert second.output_path.is_file()
    assert len(_primary_outputs(tmp_path)) == 2



def test_publish_move_failure_restores_old_artifact(tmp_path, monkeypatch):
    import ingest2md.model as model

    engine = _mock_engine(tmp_path, monkeypatch, ["可靠覆盖", "可靠覆盖"],
                          [_time(21), _time(22)], grouped=True)
    old = asyncio.run(engine.ingest_one("https://example.com/same"))
    original_replace = model.os.replace

    def fail_publish(src, dst):
        if ".i2m-" in str(src) and Path(dst).name.startswith("20261022__"):
            raise OSError("simulated publication failure")
        return original_replace(src, dst)

    monkeypatch.setattr(model.os, "replace", fail_publish)
    with pytest.raises(OSError, match="publication failure"):
        asyncio.run(engine.ingest_one("https://example.com/same"))

    assert old.output_path.is_file()
    assert "version-0" in old.output_path.read_text(encoding="utf-8")
    assert len(_primary_outputs(tmp_path)) == 1


def test_index_date_uses_same_beijing_day_as_output(tmp_path, monkeypatch):
    utc_evening = datetime(2026, 10, 21, 20, tzinfo=timezone.utc)
    engine = _mock_engine(tmp_path, monkeypatch, ["跨时区"], [utc_evening])
    result = asyncio.run(engine.ingest_one("https://example.com/time"))
    assert result.output_path.name == "20261022__跨时区.md"
    assert "2026-10-22" in (tmp_path / "sources.md").read_text(encoding="utf-8")



def test_title_overwrite_from_different_url_replaces_stale_index_row(tmp_path, monkeypatch):
    engine = _mock_engine(tmp_path, monkeypatch, ["相同内容", "相同内容"],
                          [_time(21), _time(22)])
    old = asyncio.run(engine.ingest_one("https://example.com/old"))
    new = asyncio.run(engine.ingest_one("https://example.com/new"))
    assert not old.output_path.exists()
    assert new.output_path.is_file()
    index = (tmp_path / "sources.md").read_text(encoding="utf-8")
    assert "https://example.com/new" in index
    assert "https://example.com/old" not in index
    assert "20261021__相同内容.md" not in index



def test_batch_resume_paths_are_repaired_after_title_replacement(tmp_path, monkeypatch):
    from ingest2md.batch.models import BatchItem, config_fingerprint
    from ingest2md.batch.store import TaskStore

    engine = _mock_engine(tmp_path, monkeypatch, ["批量同名", "批量同名"],
                          [_time(21), _time(22)])
    first_url, second_url = "https://example.com/first", "https://example.com/second"
    store = TaskStore(tmp_path / "batch.sqlite3")
    try:
        ids = store.register([BatchItem(first_url), BatchItem(second_url)],
                             config_fingerprint(engine.settings))
        first = asyncio.run(engine.ingest_one(first_url))
        store.mark_success(ids[0], first)
        second = asyncio.run(engine.ingest_one(second_url))
        store.mark_success(ids[1], second)

        store.refresh_missing_outputs(ids)
        assert store.summary(ids).success == 2
        rows = store.db.execute(
            "SELECT output_path FROM tasks WHERE id IN (?, ?) ORDER BY id", ids
        ).fetchall()
        assert [row["output_path"] for row in rows] == [str(second.output_path)] * 2
    finally:
        store.close()
