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
    assert "| 链接 | Extractor | 产物路径 | 日期 |" in text
    assert "| https://example.com/a | WebExtractor | `文章A.md` | 2026-01-01 |" in text


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
