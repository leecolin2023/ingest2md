"""sources.md 索引的行为测试：创建、去重更新、保留手写区块。"""
import subprocess
import sys
from pathlib import Path

import pytest

from ingest2md.source_index import record_source


def test_creates_index_with_first_row(tmp_path: Path):
    index = record_source(
        tmp_path, "https://example.com/a", "WebExtractor",
        tmp_path / "文章A.md", date="2026-01-01",
    )
    text = index.read_text(encoding="utf-8")
    assert index == tmp_path / "sources.md"
    assert text.startswith("# 转写链接记录")
    assert "| 链接 | Extractor | 产物路径 | 日期 | 是否已精读 |" in text
    assert "| https://example.com/a | WebExtractor | `文章A.md` | 2026-01-01 | 否 |" in text


def test_updates_row_by_link_and_by_product_name(tmp_path: Path):
    record_source(tmp_path, "https://www.douyin.com/video/123", "DouyinExtractor",
                  tmp_path / "标题A__123.md", date="2026-01-01")
    record_source(tmp_path, "https://example.com/x", "WebExtractor",
                  tmp_path / "文章B.md", date="2026-01-02")
    # 同一链接（尾斜杠差异）应更新原行
    record_source(tmp_path, "https://www.douyin.com/video/123/", "DouyinExtractor",
                  tmp_path / "标题A__123.md", date="2026-01-03")
    # 同产物文件名（分享短链形式）应更新同一行而不是新增
    record_source(tmp_path, "https://v.douyin.com/abc/", "DouyinExtractor",
                  tmp_path / "标题A__123.md", date="2026-01-04")

    rows = [
        line for line in (tmp_path / "sources.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| ") and " 链接 " not in line and "---" not in line
    ]
    assert len(rows) == 2
    assert "2026-01-04" in rows[0]
    assert "https://example.com/x" in rows[1]


def test_preserves_handwritten_sections(tmp_path: Path):
    record_source(tmp_path, "https://example.com/a", "WebExtractor",
                  tmp_path / "文章A.md", date="2026-01-01")
    index = tmp_path / "sources.md"
    index.write_text(
        index.read_text(encoding="utf-8") + "\n## 备注\n\n- 手写内容\n",
        encoding="utf-8",
    )
    record_source(tmp_path, "https://example.com/b", "WebExtractor",
                  tmp_path / "文章B.md", date="2026-01-02")
    text = index.read_text(encoding="utf-8")
    assert "## 备注" in text
    assert "- 手写内容" in text
    assert "文章B.md" in text


def _data_rows(index: Path) -> list[str]:
    return [
        line for line in index.read_text(encoding="utf-8").splitlines()
        if line.startswith("| ") and " 链接 " not in line and "---" not in line
    ]


def test_distinct_case_sensitive_urls_do_not_collide(tmp_path: Path):
    record_source(tmp_path, "HTTPS://Example.COM/ReportA", "WebExtractor", tmp_path / "A.md")
    record_source(tmp_path, "https://example.com/reporta", "WebExtractor", tmp_path / "B.md")
    assert len(_data_rows(tmp_path / "sources.md")) == 2
    # Scheme/host case and trailing slash may vary without changing the resource.
    record_source(tmp_path, "https://EXAMPLE.com/ReportA/", "WebExtractor", tmp_path / "A.md")
    assert len(_data_rows(tmp_path / "sources.md")) == 2


def test_same_basename_in_distinct_directories_is_not_a_collision(tmp_path: Path):
    record_source(tmp_path, "https://example.com/one", "A", tmp_path / "one" / "report.md")
    record_source(tmp_path, "https://example.com/two", "B", tmp_path / "two" / "report.md")
    rows = _data_rows(tmp_path / "sources.md")
    assert len(rows) == 2
    assert "`one/report.md`" in rows[0] and "`two/report.md`" in rows[1]


def test_unrelated_sources_md_must_not_be_corrupted(tmp_path: Path):
    index = tmp_path / "sources.md"
    original = "# unrelated source document\\nMy private notes\\n".replace("\\n", "\n")
    index.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="non-index document"):
        record_source(tmp_path, "https://example.com/one", "A", tmp_path / "one.md")
    assert index.read_text(encoding="utf-8") == original


def test_replace_failure_keeps_previous_index(tmp_path: Path, monkeypatch):
    index = record_source(tmp_path, "https://example.com/a", "A", tmp_path / "a.md")
    before = index.read_bytes()

    def reject(*args):
        raise OSError("forced replace failure")

    monkeypatch.setattr("ingest2md.source_index.os.replace", reject)
    with pytest.raises(OSError, match="forced replace failure"):
        record_source(tmp_path, "https://example.com/b", "B", tmp_path / "b.md")
    assert index.read_bytes() == before
    assert not list(tmp_path.glob(".sources.md.*.tmp"))


def test_four_real_processes_do_not_lose_updates(tmp_path: Path):
    # Exercise OS-level contention; a threading test would miss lost updates
    # between separate CLI/batch invocations.
    code = (
        "import sys; from pathlib import Path; "
        "from ingest2md.source_index import record_source; "
        "root=Path(sys.argv[1]); group=int(sys.argv[2]); "
        "[record_source(root, f'https://example.com/{group}/{i}', 'Worker', "
        "root/f'{group}_{i}.md') for i in range(12)]"
    )
    repo_root = Path(__file__).resolve().parents[1]
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path), str(worker)],
            cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for worker in range(4)
    ]
    for process in processes:
        _, stderr = process.communicate(timeout=40)
        assert process.returncode == 0, stderr

    rows = _data_rows(tmp_path / "sources.md")
    assert len(rows) == 48
    for group in range(4):
        for index in range(12):
            assert any(f"https://example.com/{group}/{index} " in row for row in rows)
    assert not list(tmp_path.glob(".sources.md.*.tmp"))


def test_migrates_legacy_four_column_source_index(tmp_path: Path):
    old = ("# 转写链接记录\n\n| 链接 | Extractor | 产物路径 | 日期 |\n"
           "|---|---|---|---|\n"
           "| https://example.com/a | WebExtractor | `A.md` | 2026-01-01 |\n")
    (tmp_path / "sources.md").write_text(old, encoding="utf-8")
    record_source(tmp_path, "https://example.com/b", "WebExtractor", tmp_path / "B.md")
    lines = (tmp_path / "sources.md").read_text(encoding="utf-8")
    assert "| 是否已精读 |" in lines
    assert "A.md` | 2026-01-01 | 否 |" in lines


def test_skill_status_sync_on_mixed_sources(tmp_path: Path):
    from ingest2md.processing_status import sync_processing_status
    output = tmp_path / "output"
    refined = tmp_path / "output-Refinement"
    learning = tmp_path / "output-Learning"
    for d in (output, refined, learning):
        d.mkdir()
    local = output / "20261026__A"
    local.mkdir()
    (local / "content.md").write_text("# A\n", encoding="utf-8")
    direct = output / "20261026__B.md"
    direct.write_text("# B\n", encoding="utf-8")
    result = sync_processing_status(output)
    assert result == dict(total=2, learning=0, refinement=0, partial=0, unread=2)
    (learning / "20261026__A__DeepRead.md").write_text("# Deep\n", encoding="utf-8")
    (learning / "20261026__A__Learning.md").write_text("# Learning\n", encoding="utf-8")
    (refined / "20261026__B.md").write_text("# Refine\n", encoding="utf-8")
    result = sync_processing_status(output)
    assert result["unread"] == 0
    assert result["learning"] == 1 and result["refinement"] == 1
    lines = (output / "sources.md").read_text(encoding="utf-8")
    assert lines.count(" | 是 |") == 2
    assert "`20261026__A/content.md`" in lines
    (learning / "20261026__A__Learning.md").unlink()
    result = sync_processing_status(output)
    assert result["unread"] == 1 and result["partial"] == 1


def test_legacy_refinement_readme_mapping(tmp_path: Path):
    from ingest2md.processing_status import sync_processing_status
    out = tmp_path / "output"; out.mkdir()
    ref = tmp_path / "output-Refinement"; ref.mkdir()
    (out / "旧题__123.md").write_text("# Old\n", encoding="utf-8")
    (ref / "20261016__旧题.md").write_text("# Refined\n", encoding="utf-8")
    (ref / "README.md").write_text(
        "| [原稿](../output/%E6%97%A7%E9%A2%98__123.md) | "
        "[20261016__旧题.md](./20261016__%E6%97%A7%E9%A2%98.md) |\n", encoding="utf-8")
    result = sync_processing_status(out)
    assert result["refinement"] == 1 and result["unread"] == 0
