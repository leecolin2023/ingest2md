"""默认入口的批量路由：非文件输入写入 <输出目录>/source.txt 后走批量入口。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import ingest2md.cli as cli


def test_should_route_to_batch_by_input_kind(tmp_path: Path):
    media = tmp_path / "meeting.mp4"
    media.write_bytes(b"x")
    manifest = tmp_path / "sources.txt"
    manifest.write_text("https://example.com/a\n", encoding="utf-8")

    assert cli._should_route_to_batch("https://v.douyin.com/OXhowLhRHo8/") is True
    assert cli._should_route_to_batch(
        "8.20 复制打开抖音，看看【作者】标题 https://v.douyin.com/OXhowLhRHo8/ :6pm"
    ) is True
    assert cli._should_route_to_batch(str(manifest)) is True
    assert cli._should_route_to_batch(str(media)) is False


def test_non_file_input_writes_output_source_txt_and_uses_batch(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute_batch", lambda args: calls.append(args) or 0)

    config = tmp_path / "config.yaml"
    config.write_text("{}\n", encoding="utf-8")
    out = tmp_path / "out"
    share_text = "8.20 复制打开抖音，看看【作者】标题 https://v.douyin.com/OXhowLhRHo8/ :6pm"

    rc = cli.single_main([share_text, "--config", str(config), "-o", str(out)])

    assert rc == 0
    manifest = out / "source.txt"
    assert manifest.read_text(encoding="utf-8") == f"{share_text}\n"
    assert len(calls) == 1
    batch_args = calls[0]
    assert batch_args.manifest == str(manifest)
    assert batch_args.resume is False
    assert batch_args.take == 0
    assert batch_args.retry_failed is False
    assert batch_args.state_db is None


def test_source_txt_is_cleared_before_each_run(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_execute_batch", lambda args: 0)

    config = tmp_path / "config.yaml"
    config.write_text("{}\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "source.txt"
    stale.write_text("https://example.com/old\nhttps://example.com/older\n", encoding="utf-8")

    rc = cli.single_main(["https://example.com/new", "--config", str(config), "-o", str(out)])

    assert rc == 0
    assert stale.read_text(encoding="utf-8") == "https://example.com/new\n"


def test_manifest_file_input_goes_directly_to_batch(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute_batch", lambda args: calls.append(args) or 0)

    links = tmp_path / "links.txt"
    links.write_text("https://example.com/a\n", encoding="utf-8")

    rc = cli.single_main([str(links)])

    assert rc == 0
    assert len(calls) == 1
    assert calls[0].manifest == str(links)
    assert not (tmp_path / "output" / "source.txt").exists()


def test_local_media_file_keeps_single_ingestion(tmp_path: Path, monkeypatch):
    media = tmp_path / "meeting.mp4"
    media.write_bytes(b"x")
    config = tmp_path / "config.yaml"
    config.write_text("{}\n", encoding="utf-8")

    async def fake_single(settings, source):
        return SimpleNamespace(
            source_name="Fake",
            output_path=tmp_path / "meeting.md",
            document=SimpleNamespace(image_map={}),
        ), tmp_path

    def fake_batch(args):
        raise AssertionError("本地媒体文件不应走批量入口")

    monkeypatch.setattr(cli, "_run_single_ingestion", fake_single)
    monkeypatch.setattr(cli, "_execute_batch", fake_batch)

    rc = cli.single_main([str(media), "--config", str(config)])

    assert rc == 0
