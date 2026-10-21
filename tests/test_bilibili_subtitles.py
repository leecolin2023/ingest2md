"""Regression tests for Bilibili subtitle-first ingestion.

All tests are offline: yt-dlp is replaced at its public YoutubeDL boundary.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ingest2md.config import Settings
from ingest2md.media.subtitles import (
    SubtitleAcquisitionError,
    fetch_yt_dlp_subtitles_with_info,
)
from ingest2md.transcription.model import Segment, TranscriptResult


SRT = (
    "1\n00:00:00,000 --> 00:00:02,500\n第一句\n\n"
    "2\n00:00:02,500 --> 00:00:05,000\n第二句\n\n"
)
VIDEO_URL = "https://www.bilibili.com/video/BV1xx411c7mD?p=1"


def _fake_ytdlp(monkeypatch, extract):
    calls = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            calls.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            assert url == VIDEO_URL
            return extract(self.options, download)

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    return calls


def _stub_bilibili_metadata(monkeypatch):
    import ingest2md.extractors.bilibili as bili

    monkeypatch.setattr(bili.source, "resolve_video", lambda url: ("BV1xx411c7mD", 1))
    monkeypatch.setattr(
        bili.source,
        "fetch_meta",
        lambda bvid, part, cookies_file="": {
            "title": "字幕测试",
            "uploader": "测试UP",
            "duration": 5,
            "desc": "",
            "url": VIDEO_URL,
            "metadata_source": "view-api",
        },
    )
    return bili


def test_probe_enables_subtitle_extraction_and_reuses_inline_srt(tmp_path, monkeypatch):
    def extract(options, download):
        assert download is False, "the inline path must not re-extract or download media"
        # Simulate Bilibili's lazy subtitle extraction: without this option
        # yt-dlp returns no subtitle list even though one exists.
        subtitles = (
            {"danmaku": [{"ext": "xml", "url": "https://example.org/danmaku.xml"}],
             "zh-Hans": [{"ext": "srt", "data": SRT}]}
            if options.get("writesubtitles") else {}
        )
        return {"subtitles": subtitles}

    calls = _fake_ytdlp(monkeypatch, extract)
    result = fetch_yt_dlp_subtitles_with_info(VIDEO_URL, tmp_path / "subtitles")
    assert result.track is not None
    assert result.track.kind == "manual"
    assert result.track.language == "zh-Hans"
    assert [cue.text for cue in result.track.cues] == ["第一句", "第二句"]
    assert len(calls) == 1, "already embedded SRT needs no second yt-dlp request"
    assert calls[0]["skip_download"] is True
    assert calls[0]["writesubtitles"] is True
    assert calls[0]["writeautomaticsub"] is True
    assert not (tmp_path / "subtitles").exists()


def test_explicitly_absent_subtitles_can_return_none(tmp_path, monkeypatch):
    calls = _fake_ytdlp(
        monkeypatch,
        lambda options, download: {"subtitles": {"danmaku": [{"ext": "xml"}]}},
    )
    result = fetch_yt_dlp_subtitles_with_info(VIDEO_URL, tmp_path / "subtitles")
    assert result.track is None
    assert len(calls) == 1


def test_url_based_subtitles_keep_existing_second_download(tmp_path, monkeypatch):
    def extract(options, download):
        if download:
            assert options["skip_download"] is True
            assert options["writesubtitles"] is True
            target = Path(options["outtmpl"].replace("%(ext)s", "srt"))
            target.write_text(SRT, encoding="utf-8")
        return {"subtitles": {"en": [{"ext": "srt", "url": "https://example.org/en.srt"}]}}

    calls = _fake_ytdlp(monkeypatch, extract)
    result = fetch_yt_dlp_subtitles_with_info(VIDEO_URL, tmp_path / "subtitles")
    assert [cue.text for cue in result.track.cues] == ["第一句", "第二句"]
    assert len(calls) == 2


@pytest.mark.parametrize("available_srt", [None, "invalid subtitle data"])
def test_advertised_but_unusable_subtitle_is_not_absence(
    tmp_path, monkeypatch, available_srt
):
    def extract(options, download):
        if download and available_srt is not None:
            Path(options["outtmpl"].replace("%(ext)s", "srt")).write_text(
                available_srt, encoding="utf-8"
            )
        return {"subtitles": {"zh": [{"ext": "srt", "url": "https://example.org/zh.srt"}]}}

    _fake_ytdlp(monkeypatch, extract)
    with pytest.raises(SubtitleAcquisitionError):
        fetch_yt_dlp_subtitles_with_info(VIDEO_URL, tmp_path / "subtitles")


def test_bilibili_adapter_inline_srt_skips_audio_and_asr(tmp_path, monkeypatch):
    bili = _stub_bilibili_metadata(monkeypatch)
    calls = _fake_ytdlp(
        monkeypatch,
        lambda options, download: {"subtitles": {"zh-Hans": [{"ext": "srt", "data": SRT}]}},
    )
    def forbidden(*args, **kwargs):
        raise AssertionError("available subtitles must not download audio or invoke ASR")

    monkeypatch.setattr(bili.source, "download_audio", forbidden)
    monkeypatch.setattr(bili, "transcribe_audio", forbidden)

    doc = asyncio.run(bili.BilibiliExtractor(Settings(output_dir=str(tmp_path))).extract(
        VIDEO_URL, tmp_path
    ))
    assert len(calls) == 1
    assert calls[0]["http_headers"]["Referer"] == "https://www.bilibili.com/"
    assert doc.transcript.models == ["manual-subtitle:zh-Hans"]
    assert doc.transcript.timestamp_precision == "subtitle-window"
    assert "第一句" in doc.body_md and "第二句" in doc.body_md
    assert "### 00:00–00:05" in doc.body_md
    assert dict(doc.metadata)["内容获取"].startswith("平台字幕")


def test_bilibili_adapter_proven_no_subtitles_uses_asr(tmp_path, monkeypatch):
    bili = _stub_bilibili_metadata(monkeypatch)
    _fake_ytdlp(
        monkeypatch,
        lambda options, download: {"subtitles": {"danmaku": [{"ext": "xml"}]}},
    )
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"fake")
    called = {"asr": 0, "audio": 0}

    def audio_download(*args, **kwargs):
        called["audio"] += 1
        return str(audio)

    def fake_asr(*args, **kwargs):
        called["asr"] += 1
        return TranscriptResult([Segment(0, 5, "ASR 结果")], ["mock-asr"], 5)

    monkeypatch.setattr(bili.source, "download_audio", audio_download)
    monkeypatch.setattr(bili, "transcribe_audio", fake_asr)
    doc = asyncio.run(bili.BilibiliExtractor(Settings(output_dir=str(tmp_path))).extract(
        VIDEO_URL, tmp_path
    ))
    assert called == {"audio": 1, "asr": 1}
    assert "ASR 结果" in doc.body_md
    assert "ASR fallback" in dict(doc.metadata)["内容获取"]


@pytest.mark.parametrize("error", [RuntimeError("HTTP 412"), TimeoutError("subtitle API timeout")])
def test_bilibili_adapter_probe_error_never_starts_asr(
    tmp_path, monkeypatch, error
):
    bili = _stub_bilibili_metadata(monkeypatch)

    def fail_probe(options, download):
        raise error

    _fake_ytdlp(monkeypatch, fail_probe)

    def forbidden(*args, **kwargs):
        raise AssertionError("failed probe is not proof of no subtitles")

    monkeypatch.setattr(bili.source, "download_audio", forbidden)
    monkeypatch.setattr(bili, "transcribe_audio", forbidden)

    with pytest.raises(RuntimeError, match="字幕探测失败") as excinfo:
        asyncio.run(bili.BilibiliExtractor(Settings(output_dir=str(tmp_path))).extract(
            VIDEO_URL, tmp_path
        ))
    assert excinfo.value.__cause__ is error
