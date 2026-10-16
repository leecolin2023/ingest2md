"""sources.md 索引的行为测试：创建、去重更新、保留手写区块。"""
from pathlib import Path

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
