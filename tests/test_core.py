from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ingest2md.browser import load_netscape_cookies
from ingest2md.config import Settings
from ingest2md.extractors.base import SourceUnavailableError
from ingest2md.extractors.deferred_media import DeferredMediaExtractor
from ingest2md.extractors.local_media import LocalMediaExtractor
from ingest2md.extractors.web import GenericWebExtractor, parse_web_page
from ingest2md.extractors.xiaoyuzhou import XiaoyuzhouExtractor, parse_episode_page
from ingest2md.model import Document, write_document
from ingest2md.router import find_extractor
from ingest2md.transcription.model import Segment, TranscriptResult
from ingest2md.transcription.writers import render_markdown
from ingest2md.urlutils import extract_first_url, normalize_reference, normalize_url


SHARE_TEXT = """6.48 复制打开抖音，看看【星彩她爹讲三国（张睿）的作品】
https://v.douyin.com/akR8LCIaTMI/
m@Q.xS Xmq:/ :0pm 12/04"""

NEXT_DATA_HTML = r'''<!doctype html><html><head>
<title>Vol.1 AI最前沿的人已经不聊大模型了 - 易论AI | 小宇宙</title>
<meta property="og:title" content="fallback title" />
</head><body>
<script id="__NEXT_DATA__" type="application/json">{
  "props": {"pageProps": {"episode": {
    "eid": "6aa127229d3264778166855e",
    "title": "Vol.1 AI最前沿的人已经不聊大模型了",
    "description": "节目简介文字",
    "shownotes": "<p>01:21 AI落地</p><p>15:16 AI创业</p>",
    "duration": 5580,
    "pubDate": "2026-09-09T00:00:00.000Z",
    "enclosure": {"url": "https://media.xyzcdn.net/demo/audio.m4a"},
    "podcast": {"title": "易论AI"}
  }}}
}</script>
</body></html>'''

OG_FALLBACK_HTML = '''<!doctype html><html><head>
<meta property="og:title" content="Fallback Episode" />
<meta property="og:description" content="Fallback description" />
<meta property="og:audio" content="https://media.xyzcdn.net/demo/fallback.mp3" />
<title>Fallback Episode - Fallback Podcast | 小宇宙</title>
</head><body></body></html>'''


def test_share_text_extracts_first_url():
    assert extract_first_url(SHARE_TEXT) == "https://v.douyin.com/akR8LCIaTMI/"
    assert normalize_reference(SHARE_TEXT) == "https://v.douyin.com/akR8LCIaTMI/"


def test_plain_url_behavior_is_unchanged():
    raw = "https://example.com/a?x=1&y=2"
    assert normalize_url(raw) == raw


def test_bv_still_normalizes():
    assert normalize_reference("BV1xx411c7mD") == "https://www.bilibili.com/video/BV1xx411c7mD"


def test_existing_media_file_routes_local(tmp_path: Path):
    media = tmp_path / "demo.mp4"
    media.write_bytes(b"not-real-media")
    reference = normalize_reference(str(media))
    assert reference == str(media.resolve())
    assert isinstance(find_extractor(reference), LocalMediaExtractor)


def test_nonexistent_media_path_is_not_local(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reference = normalize_reference("missing.mp4")
    assert reference == "https://missing.mp4"
    assert not isinstance(find_extractor(reference), LocalMediaExtractor)


def test_douyin_is_intercepted_before_generic():
    extractor = find_extractor(normalize_reference(SHARE_TEXT))
    assert isinstance(extractor, DeferredMediaExtractor)
    with pytest.raises(SourceUnavailableError, match="抖音视频"):
        asyncio.run(extractor.extract("https://v.douyin.com/akR8LCIaTMI/", Path(".")))


def test_weixin_channel_is_intercepted():
    extractor = find_extractor("https://weixin.qq.com/sph/abc123")
    assert isinstance(extractor, DeferredMediaExtractor)
    with pytest.raises(SourceUnavailableError, match="微信视频号"):
        asyncio.run(extractor.extract("https://weixin.qq.com/sph/abc123", Path(".")))


def test_xiaoyuzhou_routes_before_generic():
    url = "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e"
    assert isinstance(find_extractor(url), XiaoyuzhouExtractor)


def test_xiaoyuzhou_next_data_parser():
    url = "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e"
    meta = parse_episode_page(NEXT_DATA_HTML, url)
    assert meta["title"].startswith("Vol.1")
    assert meta["podcast_title"] == "易论AI"
    assert meta["duration"] == 5580
    assert meta["audio_url"] == "https://media.xyzcdn.net/demo/audio.m4a"
    assert "01:21 AI落地" in meta["shownotes_md"]


def test_xiaoyuzhou_og_meta_fallback():
    url = "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e"
    meta = parse_episode_page(OG_FALLBACK_HTML, url)
    assert meta["title"] == "Fallback Episode"
    assert meta["audio_url"].endswith("fallback.mp3")
    assert meta["description"] == "Fallback description"
    assert meta["podcast_title"] == "Fallback Podcast"


def test_xiaoyuzhou_extractor_calls_shared_transcription(tmp_path: Path, monkeypatch):
    import ingest2md.extractors.xiaoyuzhou as xyz

    called = {"transcribe": False, "audio_url": ""}
    monkeypatch.setattr(xyz, "_ffmpeg_bin", lambda name: name)
    monkeypatch.setattr(xyz, "fetch_episode_page", lambda url: NEXT_DATA_HTML)

    def fake_download(url, target, **kwargs):
        called["audio_url"] = url
        target.write_bytes(b"fake")
        return target

    def fake_transcribe(audio_path, work, settings):
        called["transcribe"] = True
        return TranscriptResult(
            [Segment(0, 60, "中文转写", "original")],
            ["mock-asr"], 60, translation_models=["mock-translation"],
        )

    monkeypatch.setattr(xyz, "download_url", fake_download)
    monkeypatch.setattr(xyz, "transcribe_audio", fake_transcribe)

    settings = Settings(api_key="test", output_dir=str(tmp_path))
    doc = asyncio.run(XiaoyuzhouExtractor(settings).extract(
        "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e", tmp_path
    ))
    assert called["transcribe"] is True
    assert called["audio_url"] == "https://media.xyzcdn.net/demo/audio.m4a"
    assert "## Show Notes" in doc.body_md
    assert "01:21 AI落地" in doc.body_md
    assert "## 转写正文" in doc.body_md
    assert "中文转写" in doc.body_md


def test_default_write_is_markdown_only(tmp_path: Path):
    doc = Document(title="demo", source_url="https://example.com", body_md="body")
    path = write_document(doc, tmp_path, ("md",))
    assert path.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo.md"]


def test_explicit_json_groups_output(tmp_path: Path):
    doc = Document(title="demo", source_url="https://example.com", body_md="body")
    path = write_document(doc, tmp_path, ("md", "json"))
    assert path.parent.name == "demo"
    assert (path.parent / "document.json").exists()


def test_generic_web_article_parse():
    html = "<html><head><title>A</title></head><body><article><h1>T</h1><p>" + ("正文" * 80) + "</p></article></body></html>"
    doc = parse_web_page(html, "https://example.com/article")
    assert doc.title == "A"
    assert "正文" in doc.body_md
    assert isinstance(find_extractor("https://example.com/article"), GenericWebExtractor)


def test_video_time_headings_regression():
    transcript = TranscriptResult([Segment(0, 300, "第一段"), Segment(300, 601, "第二段")], ["m"], 601)
    md = render_markdown(transcript)
    assert "### 00:00–05:00" in md
    assert "### 05:00–10:01" in md


def test_netscape_cookie_parser_regression(tmp_path: Path):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text(".example.com\tTRUE\t/\tTRUE\t1893456000\tsid\tsecret\n", encoding="utf-8")
    items = load_netscape_cookies(str(cookie), "example.com")
    assert len(items) == 1
    assert items[0]["name"] == "sid"
    assert items[0]["secure"] is True
