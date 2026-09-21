from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ingest2md.browser import load_netscape_cookies
from ingest2md.cookies import parse_netscape_cookie_file
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
from ingest2md.urlutils import extract_first_url, extract_references, normalize_reference, normalize_url


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
    from ingest2md.extractors.douyin import DouyinExtractor

    extractor = find_extractor(normalize_reference(SHARE_TEXT))
    assert isinstance(extractor, DouyinExtractor)


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
    monkeypatch.setattr(xyz, "fetch_episode_page", lambda url: NEXT_DATA_HTML)

    def fake_download(url, target, **kwargs):
        called["audio_url"] = url
        target.write_bytes(b"fake")
        return target

    def fake_transcribe(audio_path, work, settings):
        called["transcribe"] = True
        return TranscriptResult(
            [Segment(0, 60, "中文转写")],
            ["mock-asr"], 60,
        )

    monkeypatch.setattr(xyz, "download_url", fake_download)
    monkeypatch.setattr(xyz, "probe_media_info", lambda path: {
        "duration": 5580,
        "has_audio": True,
        "has_video": False,
    })
    monkeypatch.setattr(xyz, "transcribe_audio", fake_transcribe)

    settings = Settings(output_dir=str(tmp_path))
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




def test_markdown_groups_low_level_asr_chunks():
    transcript = TranscriptResult(
        [
            Segment(0, 30, "第一段"),
            Segment(30, 60, "第二段"),
            Segment(270, 300, "第十段"),
            Segment(300, 330, "下一窗口"),
        ],
        ["m"],
        330,
    )
    md = render_markdown(transcript, window_seconds=300)
    assert md.count("### ") == 2
    assert "### 00:00–05:00" in md
    assert "第一段" in md and "第十段" in md
    assert "### 05:00–05:30" in md
    assert "下一窗口" in md


def test_xiaoyuzhou_parses_shownote_chapters():
    from ingest2md.extractors.xiaoyuzhou import parse_shownote_chapters

    shownotes = """
- 01:21 AI 落地
- [15:16](https://example.com/t=916) AI 创业
### 1:02:03 Agent 架构
普通说明文字
"""
    assert parse_shownote_chapters(shownotes) == [
        (81.0, "AI 落地"),
        (916.0, "AI 创业"),
        (3723.0, "Agent 架构"),
    ]


def test_chaptered_markdown_uses_semantic_titles():
    from ingest2md.transcription.writers import render_chaptered_markdown

    transcript = TranscriptResult(
        [
            Segment(0, 30, "开场内容"),
            Segment(60, 90, "第一章之前"),
            Segment(90, 120, "AI 落地正文"),
            Segment(920, 930, "AI 创业正文"),
        ],
        ["m"],
        930,
    )
    md = render_chaptered_markdown(
        transcript,
        [(81, "AI 落地"), (916, "AI 创业")],
        window_seconds=300,
    )
    assert "### 00:00 开场" in md
    assert "### 01:21 AI 落地" in md
    assert "### 15:16 AI 创业" in md
    assert "AI 落地正文" in md
    assert "AI 创业正文" in md


def test_xiaoyuzhou_rejects_truncated_audio_before_asr(tmp_path: Path, monkeypatch):
    import ingest2md.extractors.xiaoyuzhou as xyz

    monkeypatch.setattr(xyz, "fetch_episode_page", lambda url: NEXT_DATA_HTML)

    def fake_download(url, target, **kwargs):
        target.write_bytes(b"fake")
        return target

    monkeypatch.setattr(xyz, "download_url", fake_download)
    monkeypatch.setattr(xyz, "probe_media_info", lambda path: {
        "duration": 120,
        "has_audio": True,
        "has_video": False,
    })
    monkeypatch.setattr(
        xyz, "transcribe_audio",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("truncated podcast must fail before ASR")
        ),
    )

    with pytest.raises(RuntimeError, match="明显不完整"):
        asyncio.run(XiaoyuzhouExtractor(Settings(output_dir=str(tmp_path))).extract(
            "https://www.xiaoyuzhoufm.com/episode/6aa127229d3264778166855e",
            tmp_path,
        ))


def test_netscape_cookie_parser_regression(tmp_path: Path):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text(".example.com\tTRUE\t/\tTRUE\t1893456000\tsid\tsecret\n", encoding="utf-8")
    items = load_netscape_cookies(str(cookie), "example.com")
    assert len(items) == 1
    assert items[0]["name"] == "sid"
    assert items[0]["secure"] is True


def test_document_routes_before_generic(tmp_path: Path):
    from ingest2md.extractors.document import DocumentExtractor

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-fake")
    reference = normalize_reference(str(pdf))
    assert isinstance(find_extractor(reference), DocumentExtractor)
    assert isinstance(find_extractor("https://example.com/report.docx"), DocumentExtractor)


def test_explain_route_is_dry_and_source_aware():
    from ingest2md.router import explain_route, format_route_explanation

    report = explain_route("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert report["source"] == "YouTube 视频"
    assert report["adapter"] == "YouTubeExtractor"
    assert any("字幕" in step for step in report["plan"])
    text = format_route_explanation(report)
    assert "dry-run" in text
    assert "未抓取、未下载、未调用模型" in text


def test_generic_web_prefers_trafilatura(monkeypatch):
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "trafilatura", SimpleNamespace(
        extract=lambda html, **kwargs: "# Trafilatura\n\nclean body"
    ))
    html = "<html><head><title>A</title></head><body><article>legacy body</article></body></html>"
    doc = parse_web_page(html, "https://example.com/article")
    assert doc.body_md.startswith("# Trafilatura")
    assert "clean body" in doc.body_md


def test_subtitle_parser_and_grouping():
    from ingest2md.media.subtitles import SubtitleTrack, parse_vtt_or_srt
    from ingest2md.transcription.subtitles import subtitles_to_transcript

    vtt = """WEBVTT

00:00:00.000 --> 00:00:02.000
Hello

00:00:02.000 --> 00:00:04.000
world
"""
    cues = parse_vtt_or_srt(vtt)
    assert [cue.text for cue in cues] == ["Hello", "world"]

    track = SubtitleTrack(language="en", kind="manual", cues=cues)
    result = subtitles_to_transcript(track, Settings(subtitle_window_seconds=300))
    assert result.models == ["manual-subtitle:en"]
    assert result.timestamp_precision == "subtitle-window"
    assert result.language == "en"
    assert result.segments[0].text == "Hello world"


def test_youtube_subtitle_first_skips_probe_audio_and_asr(tmp_path: Path, monkeypatch):
    import ingest2md.extractors.youtube as yt
    from ingest2md.media.subtitles import SubtitleCue, SubtitleFetchResult, SubtitleTrack

    track = SubtitleTrack("en", "manual", [SubtitleCue(0, 10, "hello")])
    info = {
        "id": "dQw4w9WgXcQ", "title": "Demo", "uploader": "Channel",
        "duration": 10, "description": "Desc", "formats": [],
    }
    monkeypatch.setattr(
        yt, "fetch_yt_dlp_subtitles_with_info",
        lambda *args, **kwargs: SubtitleFetchResult(track=track, info=info),
    )
    monkeypatch.setattr(
        yt.source, "probe_playback_access",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("normal ingestion must not call probe_video")
        ),
    )
    transcript = TranscriptResult(
        [Segment(0, 10, "hello")], ["manual-subtitle:en"], 10,
        timestamp_precision="subtitle-window", language="en",
    )
    monkeypatch.setattr(yt, "subtitles_to_transcript", lambda *args, **kwargs: transcript)
    monkeypatch.setattr(yt, "transcribe_audio", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("ASR should not run when subtitles exist")
    ))
    monkeypatch.setattr(yt.source, "download_video", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("audio should not download when subtitles exist and keep_audio is false")
    ))
    monkeypatch.setattr(yt, "attach_video_description", lambda doc, desc: None)

    settings = Settings(output_dir=str(tmp_path))
    doc = asyncio.run(yt.YouTubeExtractor(settings).extract(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path
    ))
    assert doc.title == "Demo"
    assert doc.transcript.models == ["manual-subtitle:en"]
    assert dict(doc.metadata)["内容获取"].startswith("平台字幕")


def test_youtube_without_subtitle_falls_back_to_asr(tmp_path: Path, monkeypatch):
    import ingest2md.extractors.youtube as yt
    from ingest2md.media.subtitles import SubtitleFetchResult

    info = {
        "id": "dQw4w9WgXcQ", "title": "Demo", "uploader": "Channel",
        "duration": 10, "description": "", "formats": [],
    }
    monkeypatch.setattr(
        yt, "fetch_yt_dlp_subtitles_with_info",
        lambda *args, **kwargs: SubtitleFetchResult(track=None, info=info),
    )
    monkeypatch.setattr(
        yt.source, "probe_playback_access",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("normal ingestion must not call probe_video")
        ),
    )
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"fake")
    monkeypatch.setattr(yt.source, "download_video", lambda *args, **kwargs: ({
        "id": "dQw4w9WgXcQ", "title": "Demo", "uploader": "Channel",
        "duration": 10, "desc": "", "url": args[0],
    }, str(audio)))
    transcript = TranscriptResult([Segment(0, 10, "你好")], ["mock-asr"], 10)
    called = {"asr": False}
    def fake_asr(*args, **kwargs):
        called["asr"] = True
        return transcript
    monkeypatch.setattr(yt, "transcribe_audio", fake_asr)
    monkeypatch.setattr(yt, "attach_video_description", lambda doc, desc: None)
    monkeypatch.setattr(yt, "retain_media", lambda *args, **kwargs: None)

    settings = Settings(output_dir=str(tmp_path))
    doc = asyncio.run(yt.YouTubeExtractor(settings).extract(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path
    ))
    assert called["asr"] is True
    assert dict(doc.metadata)["内容获取"] == "音频下载 + sensevoice ASR fallback"


def test_youtube_metadata_from_subtitle_info_reuses_existing_info():
    import ingest2md.media.youtube as youtube

    meta = youtube.metadata_from_info({
        "id": "abcdefghijk",
        "title": "Title",
        "channel": "Channel",
        "duration": 42,
        "description": "Description",
        "formats": [{"acodec": "opus"}, {"acodec": "none"}],
    }, "https://www.youtube.com/watch?v=abcdefghijk")
    assert meta["id"] == "abcdefghijk"
    assert meta["uploader"] == "Channel"
    assert meta["desc"] == "Description"
    assert meta["audio_formats"] == 1


def test_bilibili_subtitle_first_skips_asr(tmp_path: Path, monkeypatch):
    import ingest2md.extractors.bilibili as bili
    from ingest2md.media.subtitles import SubtitleCue, SubtitleTrack

    monkeypatch.setattr(bili.source, "resolve_video", lambda url: ("BV1xx411c7mD", 1))
    monkeypatch.setattr(bili.source, "fetch_meta", lambda bvid, part: {
        "title": "Demo", "uploader": "UP", "duration": 10, "desc": "",
        "url": "https://www.bilibili.com/video/BV1xx411c7mD?p=1",
    })
    track = SubtitleTrack("zh-Hans", "manual", [SubtitleCue(0, 10, "你好")])
    monkeypatch.setattr(bili, "fetch_yt_dlp_subtitles", lambda *args, **kwargs: track)
    transcript = TranscriptResult([Segment(0, 10, "你好")], ["manual-subtitle:zh-Hans"], 10,
                                  timestamp_precision="subtitle-window")
    monkeypatch.setattr(bili, "subtitles_to_transcript", lambda *args, **kwargs: transcript)
    monkeypatch.setattr(bili, "transcribe_audio", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("ASR should not run when subtitles exist")
    ))
    monkeypatch.setattr(bili, "attach_video_description", lambda doc, desc: None)

    settings = Settings(output_dir=str(tmp_path))
    doc = asyncio.run(bili.BilibiliExtractor(settings).extract(
        "https://www.bilibili.com/video/BV1xx411c7mD", tmp_path
    ))
    assert doc.transcript.models == ["manual-subtitle:zh-Hans"]
    assert dict(doc.metadata)["内容获取"].startswith("平台字幕")


def test_document_adapter_delegates_to_markitdown(tmp_path: Path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from ingest2md.extractors.document import DocumentExtractor

    class FakeMarkItDown:
        def __init__(self, enable_plugins=False):
            assert enable_plugins is False
        def convert(self, source):
            return SimpleNamespace(title="Converted", markdown="# Body\n\nTable")

    monkeypatch.setitem(sys.modules, "markitdown", SimpleNamespace(MarkItDown=FakeMarkItDown))
    docx = tmp_path / "demo.docx"
    docx.write_bytes(b"fake")
    doc = asyncio.run(DocumentExtractor().extract(str(docx), tmp_path))
    assert doc.title == "Converted"
    assert doc.body_md.startswith("# Body")
    assert dict(doc.metadata)["转换后端"] == "Microsoft MarkItDown"


def test_default_asr_backend_is_local_sensevoice():
    settings = Settings()
    assert settings.asr_backend == "sensevoice"
    assert settings.sensevoice_chunk_seconds == 30
    assert settings.sensevoice_batch_size == 2
    assert settings.openai_asr_api_key == ""
    assert settings.llm_api_key == ""


def test_asr_factory_routes_three_backends():
    from ingest2md.transcription.service import create_asr_backend

    assert type(create_asr_backend(Settings(asr_backend="sensevoice"))).__name__ == "SenseVoiceBackend"
    assert type(create_asr_backend(Settings(asr_backend="openai"))).__name__ == "OpenAIASRBackend"
    assert type(create_asr_backend(Settings(asr_backend="llm"))).__name__ == "LLMAudioBackend"


def test_sensevoice_backend_owns_wav_chunking(tmp_path: Path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import ingest2md.transcription.sensevoice as sv

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    called = {"chunks": False, "model": False}

    def fake_chunks(audio, seconds, limit, out_dir):
        called["chunks"] = True
        assert seconds == 30
        chunk = tmp_path / "chunk.wav"
        chunk.write_bytes(b"fake")
        return [{"path": str(chunk), "start": 0.0, "end": 30.0}]

    class FakeModel:
        def __init__(self, path, batch_size=1, quantize=True):
            called["model"] = True
            assert batch_size == 2
        def __call__(self, paths, language="auto", use_itn=True):
            assert isinstance(paths, list)
            assert len(paths) == 1
            return ["<|zh|>本地转写"]

    monkeypatch.setattr(sv, "chunk_audio_wav", fake_chunks)
    monkeypatch.setitem(sys.modules, "funasr_onnx", SimpleNamespace(SenseVoiceSmall=FakeModel))
    monkeypatch.setitem(
        sys.modules, "funasr_onnx.utils.postprocess_utils",
        SimpleNamespace(rich_transcription_postprocess=lambda text: text.replace("<|zh|>", "")),
    )

    result = sv.SenseVoiceBackend().transcribe(
        str(tmp_path / "audio.mp3"), tmp_path,
        Settings(sensevoice_model_dir=str(model_dir)),
    )
    assert called == {"chunks": True, "model": True}
    assert result.segments[0].text == "本地转写"
    assert result.models == ["sensevoice-onnx:SenseVoiceSmall"]


def test_sensevoice_true_batching_preserves_chunk_order(tmp_path: Path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import ingest2md.transcription.sensevoice as sv

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    chunks = []
    for index in range(5):
        path = tmp_path / f"chunk_{index:04d}.wav"
        path.write_bytes(b"fake")
        chunks.append({
            "path": str(path),
            "start": float(index * 30),
            "end": float((index + 1) * 30),
        })

    monkeypatch.setattr(sv, "chunk_audio_wav", lambda *args, **kwargs: chunks)
    calls = []

    class FakeModel:
        def __init__(self, path, batch_size=1, quantize=True):
            assert batch_size == 2

        def __call__(self, paths, language="auto", use_itn=True):
            calls.append([Path(path).name for path in paths])
            return [f"<|zh|>文本-{Path(path).stem}" for path in paths]

    monkeypatch.setitem(sys.modules, "funasr_onnx", SimpleNamespace(SenseVoiceSmall=FakeModel))
    monkeypatch.setitem(
        sys.modules, "funasr_onnx.utils.postprocess_utils",
        SimpleNamespace(rich_transcription_postprocess=lambda text: text.replace("<|zh|>", "")),
    )

    result = sv.SenseVoiceBackend().transcribe(
        str(tmp_path / "audio.mp3"),
        tmp_path,
        Settings(
            sensevoice_model_dir=str(model_dir),
            sensevoice_chunk_seconds=30,
            sensevoice_batch_size=2,
        ),
    )

    assert [len(call) for call in calls] == [2, 2, 1]
    assert [segment.text for segment in result.segments] == [
        "文本-chunk_0000",
        "文本-chunk_0001",
        "文本-chunk_0002",
        "文本-chunk_0003",
        "文本-chunk_0004",
    ]
    assert [(segment.start, segment.end) for segment in result.segments] == [
        (0.0, 30.0),
        (30.0, 60.0),
        (60.0, 90.0),
        (90.0, 120.0),
        (120.0, 150.0),
    ]


def test_audio_chunker_uses_one_ffmpeg_process(tmp_path: Path, monkeypatch):
    import ingest2md.media.audio as audio

    source = tmp_path / "source.m4a"
    source.write_bytes(b"fake")
    out_dir = tmp_path / "chunks"
    calls = []

    monkeypatch.setattr(audio, "probe_duration", lambda path: 65.0)
    monkeypatch.setattr(audio, "_ffmpeg_bin", lambda name: name)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        pattern = Path(cmd[-1])
        pattern.parent.mkdir(parents=True, exist_ok=True)
        for index in range(3):
            Path(str(pattern).replace("%04d", f"{index:04d}")).write_bytes(b"fake")
        return None

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    chunks = audio.chunk_audio_wav(str(source), 30, 0, out_dir)

    assert len(calls) == 1
    assert "-f" in calls[0] and "segment" in calls[0]
    assert [item["start"] for item in chunks] == [0.0, 30.0, 60.0]
    assert [item["end"] for item in chunks] == [30.0, 60.0, 65.0]


def test_openai_asr_backend_owns_mp3_chunking(tmp_path: Path, monkeypatch):
    import ingest2md.transcription.openai_asr as cloud

    chunk = tmp_path / "chunk.mp3"
    chunk.write_bytes(b"fake")
    monkeypatch.setattr(cloud, "chunk_audio_mp3", lambda *args, **kwargs: [
        {"path": str(chunk), "start": 0.0, "end": 10.0}
    ])

    class Response:
        status_code = 200
        text = ""
        def json(self):
            return {"text": "cloud transcript"}

    monkeypatch.setattr(cloud.requests, "post", lambda *args, **kwargs: Response())
    settings = Settings(
        asr_backend="openai",
        openai_asr_api_key="test",
        openai_asr_model="demo-asr",
    )
    result = cloud.OpenAIASRBackend().transcribe("audio.mp3", tmp_path, settings)
    assert result.segments[0].text == "cloud transcript"
    assert result.models == ["demo-asr"]


def test_legacy_cloud_config_maps_to_llm_without_translation(tmp_path: Path):
    from ingest2md.config import load_settings

    config = tmp_path / "config.yaml"
    config.write_text(
        "api_key: old-key\n"
        "base_url: https://example.com/v1\n"
        "model: old-model\n"
        "translation_model: old-translate\n"
        "chunk_seconds: 123\n",
        encoding="utf-8",
    )
    settings = load_settings(str(config))
    assert settings.llm_api_key == "old-key"
    assert settings.llm_base_url == "https://example.com/v1"
    assert settings.llm_model == "old-model"
    assert settings.llm_chunk_seconds == 123
    assert not hasattr(settings, "translation_model")


def test_shared_cookie_parser_drives_browser_and_youtube_validation(tmp_path: Path):
    from ingest2md.media.youtube import validate_cookie_file

    cookie = tmp_path / "cookies.txt"
    cookie.write_text(
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tsecret\n",
        encoding="utf-8",
    )
    records = parse_netscape_cookie_file(str(cookie))
    assert len(records) == 1
    assert records[0]["domain"] == ".youtube.com"
    assert records[0]["http_only"] is True

    playwright = load_netscape_cookies(str(cookie), "youtube.com")
    assert playwright[0]["httpOnly"] is True
    assert playwright[0]["secure"] is True

    status = validate_cookie_file(str(cookie))
    assert status["valid"] is True
    assert status["domain_match"] is True
    assert status["cookie_count"] == 1


def test_registry_injects_settings_without_cli_type_list():
    from ingest2md.extractors import get_extractors
    from ingest2md.extractors.youtube import YouTubeExtractor

    settings = Settings(asr_backend="llm")
    runtime = object()
    extractors = get_extractors(settings, runtime=runtime)
    youtube = next(item for item in extractors if isinstance(item, YouTubeExtractor))
    assert youtube.settings is settings
    assert youtube.runtime is runtime


def test_douyin_routes_before_deferred_media():
    from ingest2md.extractors.douyin import DouyinExtractor
    from ingest2md.extractors.deferred_media import DeferredMediaExtractor

    extractor = find_extractor("https://v.douyin.com/abc123/")
    assert isinstance(extractor, DouyinExtractor)
    assert not isinstance(extractor, DeferredMediaExtractor)


def test_douyin_snapshot_skips_blob_and_keeps_direct_media():
    from ingest2md.media.douyin import normalize_page_snapshot

    meta = normalize_page_snapshot({
        "current_src": "blob:https://www.douyin.com/temporary",
        "src": "",
        "sources": ["https://v26-web.douyinvod.com/demo/video.mp4"],
        "title": "Demo Video",
        "author": "Demo Author",
        "description": "Demo Description",
        "canonical_url": "https://www.douyin.com/video/1234567890",
    }, "https://www.douyin.com/video/1234567890")

    assert meta["media_url"] == "https://v26-web.douyinvod.com/demo/video.mp4"
    assert meta["saw_blob"] is True
    assert meta["video_id"] == "1234567890"
    assert meta["title"] == "Demo Video"
    assert meta["author"] == "Demo Author"


def test_douyin_snapshot_collects_all_videos_and_prefers_detail_candidates():
    from ingest2md.media.douyin import normalize_page_snapshot

    meta = normalize_page_snapshot({
        "media_candidates": ["https://media.example/full.mp4"],
        "videos": [
            {"current_src": "https://static.example/placeholder.mp4"},
            {"current_src": "blob:https://www.douyin.com/real-player"},
        ],
        "canonical_url": "https://www.douyin.com/video/1234567890",
    }, "https://www.douyin.com/video/1234567890")

    assert meta["media_candidates"] == [
        "https://media.example/full.mp4",
        "https://static.example/placeholder.mp4",
    ]
    assert meta["media_url"] == "https://media.example/full.mp4"
    assert meta["saw_blob"] is True


def test_douyin_detail_snapshot_prefers_published_video_before_audio_fallback():
    from ingest2md.media.douyin import snapshot_from_aweme_detail

    snapshot = snapshot_from_aweme_detail({
        "aweme_detail": {
            "aweme_id": "1234567890",
            "desc": "水果店故事",
            "duration": 377418,
            "author": {"nickname": "刨根问底说AI"},
            "music": {
                "duration": 377,
                "play_url": {"url_list": ["https://media.example/audio.mp3"]},
            },
            "video": {
                "play_addr_h264": {"url_list": ["https://media.example/video.mp4"]},
            },
        },
    })

    assert snapshot["video_id"] == "1234567890"
    assert snapshot["author"] == "刨根问底说AI"
    assert snapshot["duration"] == pytest.approx(377.418)
    assert snapshot["media_candidates"] == [
        "https://media.example/video.mp4",
        "https://media.example/audio.mp3",
    ]


def test_douyin_extractor_reuses_browser_media_and_shared_asr(tmp_path: Path, monkeypatch):
    import ingest2md.extractors.douyin as douyin
    from ingest2md.transcription.model import Segment, TranscriptResult

    async def fake_resolve(url, cookies_file=""):
        assert url == "https://v.douyin.com/demo/"
        assert cookies_file.endswith("douyin.txt")
        return {
            "video_id": "1234567890",
            "title": "抖音测试视频",
            "author": "测试作者",
            "description": "测试简介",
            "canonical_url": "https://www.douyin.com/video/1234567890",
            "media_url": "https://v26-web.douyinvod.com/demo/video.mp4",
            "cookie_header": "sessionid=abc",
        }

    called = {"download": False, "asr": False, "headers": None}

    def fake_download(url, target, **kwargs):
        called["download"] = True
        called["headers"] = kwargs.get("headers")
        target.write_bytes(b"fake-video")
        return target

    def fake_transcribe(path, work, settings):
        called["asr"] = True
        return TranscriptResult(
            [Segment(0, 30, "测试转写")],
            ["mock-asr"],
            30,
            language="zh",
        )

    monkeypatch.setattr(douyin.source, "resolve_video_page", fake_resolve)
    monkeypatch.setattr(douyin, "download_url", fake_download)
    monkeypatch.setattr(douyin, "probe_media_info", lambda path: {
        "duration": 30,
        "has_audio": True,
        "has_video": True,
    })
    monkeypatch.setattr(douyin, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(douyin, "retain_media", lambda *args, **kwargs: None)
    async def inline_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr(douyin.asyncio, "to_thread", inline_to_thread)

    cookie_file = tmp_path / "douyin.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    settings = Settings(
        output_dir=str(tmp_path),
        douyin_cookies_file=str(cookie_file),
    )
    doc = asyncio.run(douyin.DouyinExtractor(settings).extract(
        "https://v.douyin.com/demo/", tmp_path
    ))

    assert called["download"] is True
    assert called["asr"] is True
    assert called["headers"]["Referer"] == "https://www.douyin.com/video/1234567890"
    assert called["headers"]["Cookie"] == "sessionid=abc"
    assert doc.source_type == "douyin"
    assert doc.source_id == "1234567890"
    assert doc.title == "抖音测试视频"
    assert "## 视频简介" in doc.body_md
    assert "测试简介" in doc.body_md
    assert "## 转写正文" in doc.body_md
    assert "测试转写" in doc.body_md


def test_douyin_extractor_rejects_short_candidate_and_uses_next(tmp_path: Path, monkeypatch):
    import ingest2md.extractors.douyin as douyin
    from ingest2md.transcription.model import Segment, TranscriptResult

    async def fake_resolve(url, cookies_file=""):
        return {
            "video_id": "1234567890",
            "title": "候选校验",
            "author": "",
            "description": "",
            "canonical_url": "https://www.douyin.com/video/1234567890",
            "media_url": "https://media.example/placeholder.mp4",
            "media_candidates": [
                "https://media.example/placeholder.mp4",
                "https://media.example/full.mp4",
            ],
            "cookie_header": "",
            "duration": 30.0,
            "saw_blob": True,
            "acquisition": "Playwright 浏览器详情响应",
        }

    downloads = []

    def fake_download(url, target, **kwargs):
        downloads.append(url)
        target.write_bytes(b"fake")
        return target

    def fake_probe(path):
        if "media_00" in path:
            return {"duration": 2.6, "has_audio": True, "has_video": True}
        return {"duration": 29.8, "has_audio": True, "has_video": True}

    def fake_transcribe(path, work, settings):
        assert "media_01" in path
        return TranscriptResult([Segment(0, 30, "完整音频")], ["mock-asr"], 30)

    async def inline_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(douyin.source, "resolve_video_page", fake_resolve)
    monkeypatch.setattr(douyin, "download_url", fake_download)
    monkeypatch.setattr(douyin, "probe_media_info", fake_probe)
    monkeypatch.setattr(douyin, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(douyin, "retain_media", lambda *args, **kwargs: None)
    monkeypatch.setattr(douyin.asyncio, "to_thread", inline_to_thread)

    doc = asyncio.run(douyin.DouyinExtractor(Settings(output_dir=str(tmp_path))).extract(
        "https://v.douyin.com/demo/", tmp_path
    ))

    assert downloads == [
        "https://media.example/placeholder.mp4",
        "https://media.example/full.mp4",
    ]
    assert "完整音频" in doc.body_md


def test_douyin_cookie_setting_is_loaded_relative_to_config(tmp_path: Path):
    from ingest2md.config import load_settings

    config = tmp_path / "config.yaml"
    config.write_text('douyin_cookies_file: "douyin.txt"\n', encoding="utf-8")
    settings = load_settings(str(config))
    assert settings.douyin_cookies_file == str(tmp_path / "douyin.txt")


def test_batch_loader_supports_txt_csv_jsonl(tmp_path: Path):
    from ingest2md.batch.loader import load_batch

    txt = tmp_path / "sources.txt"
    txt.write_text("# comment\nhttps://example.com/a\nBV1xx411c7mD\n", encoding="utf-8")
    assert [item.source for item in load_batch(txt)] == [
        "https://example.com/a", "BV1xx411c7mD",
    ]

    csv_file = tmp_path / "sources.csv"
    csv_file.write_text(
        "source,name,tags\nhttps://example.com/b,Article,\"web,ai\"\n",
        encoding="utf-8",
    )
    csv_items = load_batch(csv_file)
    assert csv_items[0].name == "Article"
    assert csv_items[0].tags == ("web", "ai")

    jsonl = tmp_path / "sources.jsonl"
    jsonl.write_text(
        '{"source":"https://example.com/c","name":"C","tags":["x","y"]}\n',
        encoding="utf-8",
    )
    json_items = load_batch(jsonl)
    assert json_items[0].name == "C"
    assert json_items[0].tags == ("x", "y")


def test_ingestion_engine_is_shared_single_item_core(tmp_path: Path, monkeypatch):
    import ingest2md.engine as engine_module

    class FakeExtractor:
        name = "Fake"
        async def extract(self, reference, output_dir):
            return Document(
                title="Batchable",
                source_url=reference,
                source_type="fake",
                source_id="42",
                body_md="body",
            )

    monkeypatch.setattr(engine_module, "find_extractor", lambda reference, settings=None: FakeExtractor())
    settings = Settings(output_dir=str(tmp_path))
    result = asyncio.run(engine_module.IngestionEngine(settings).ingest_one("https://example.com/x"))

    assert result.source_name == "Fake"
    assert result.canonical_key == "fake:42"
    assert result.output_path.exists()
    assert result.output_path.read_text(encoding="utf-8").startswith("# Batchable")


def test_batch_store_resume_and_retry(tmp_path: Path):
    from ingest2md.batch.models import BatchItem, config_fingerprint
    from ingest2md.batch.store import TaskStore

    settings = Settings(output_dir=str(tmp_path))
    store = TaskStore(tmp_path / "state.sqlite3")
    try:
        ids = store.register(
            [BatchItem("https://example.com/a"), BatchItem("https://example.com/a")],
            config_fingerprint(settings),
        )
        assert len(ids) == 1

        task_id = ids[0]
        store.mark_running(task_id)
        store.recover_running(ids)
        assert len(store.pending(ids)) == 1

        store.mark_failed(task_id, "timeout", "temporary")
        assert store.summary(ids).failed == 1
        store.retry_failed(ids)
        assert store.summary(ids).pending == 1
    finally:
        store.close()


def test_batch_runner_serially_isolates_failures(tmp_path: Path):
    from ingest2md.batch.models import BatchItem
    from ingest2md.batch.runner import BatchRunner
    from ingest2md.batch.store import TaskStore
    from ingest2md.engine import IngestionResult

    class FakeEngine:
        settings = Settings(output_dir=str(tmp_path))
        async def ingest_one(self, request):
            if request.source.endswith("/bad"):
                raise TimeoutError("network timeout")
            path = tmp_path / "ok.md"
            path.write_text("ok", encoding="utf-8")
            doc = Document(
                title="ok", source_url=request.source,
                source_type="web", source_id="1", body_md="ok",
            )
            return IngestionResult(
                request.source, request.source, "Fake", "web", "1", "ok",
                path, "web:1", doc,
            )

    store = TaskStore(tmp_path / "state.sqlite3")
    try:
        summary = asyncio.run(BatchRunner(FakeEngine(), store).run([
            BatchItem("https://example.com/good"),
            BatchItem("https://example.com/bad"),
        ]))
        assert summary.total == 2
        assert summary.success == 1
        assert summary.failed == 1
    finally:
        store.close()



def test_runtime_context_lazily_reuses_asr_backend(tmp_path: Path, monkeypatch):
    import ingest2md.runtime as runtime_module

    calls = []
    backend = object()

    def fake_factory(settings):
        calls.append(settings.asr_backend)
        return backend

    monkeypatch.setattr(runtime_module, "create_asr_backend", fake_factory)
    runtime = runtime_module.RuntimeContext(
        Settings(output_dir=str(tmp_path), asr_backend="sensevoice")
    )

    assert runtime.asr_backend is backend
    assert runtime.asr_backend is backend
    assert calls == ["sensevoice"]


def test_browser_context_reuses_runtime_but_closes_each_context():
    from ingest2md.browser import browser_context

    class FakeContext:
        def __init__(self, tracker):
            self.tracker = tracker
        async def close(self):
            self.tracker["closed"] += 1

    class FakeBrowserRuntime:
        def __init__(self):
            self.tracker = {"created": 0, "closed": 0}
        async def new_context(self, **kwargs):
            self.tracker["created"] += 1
            return FakeContext(self.tracker)

    async def run():
        runtime = FakeBrowserRuntime()
        async with browser_context(runtime, locale="zh-CN"):
            pass
        async with browser_context(runtime, locale="zh-CN"):
            pass
        return runtime.tracker

    assert asyncio.run(run()) == {"created": 2, "closed": 2}


def test_sensevoice_backend_reuses_loaded_model_across_files(tmp_path: Path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import ingest2md.transcription.sensevoice as sv

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    chunk = tmp_path / "chunk.wav"
    chunk.write_bytes(b"fake")
    monkeypatch.setattr(
        sv, "chunk_audio_wav",
        lambda *args, **kwargs: [{"path": str(chunk), "start": 0.0, "end": 30.0}],
    )

    init_count = {"value": 0}
    call_count = {"value": 0}

    class FakeModel:
        def __init__(self, path, batch_size=1, quantize=True):
            init_count["value"] += 1
        def __call__(self, paths, language="auto", use_itn=True):
            call_count["value"] += 1
            return ["<|zh|>复用模型"]

    monkeypatch.setitem(sys.modules, "funasr_onnx", SimpleNamespace(SenseVoiceSmall=FakeModel))
    monkeypatch.setitem(
        sys.modules, "funasr_onnx.utils.postprocess_utils",
        SimpleNamespace(rich_transcription_postprocess=lambda text: text.replace("<|zh|>", "")),
    )

    settings = Settings(
        sensevoice_model_dir=str(model_dir),
        sensevoice_batch_size=2,
    )
    backend = sv.SenseVoiceBackend()
    first = backend.transcribe("first.mp3", tmp_path / "work1", settings)
    second = backend.transcribe("second.mp3", tmp_path / "work2", settings)

    assert first.segments[0].text == "复用模型"
    assert second.segments[0].text == "复用模型"
    assert init_count["value"] == 1
    assert call_count["value"] == 2



def test_extract_references_scans_arbitrary_pasted_text():
    text = (
        "第一条 https://v.douyin.com/aaa111/ 其他文字 "
        "第二条 https://example.com/article?q=1&x=2。 "
        "B站 BV1xx411c7mD "
        "重复 https://v.douyin.com/aaa111/"
    )
    assert extract_references(text) == [
        "https://v.douyin.com/aaa111/",
        "https://example.com/article?q=1&x=2",
        "BV1xx411c7mD",
    ]
    assert extract_references(
        "课程 https://www.bilibili.com/video/BV1xx411c7mD"
    ) == ["https://www.bilibili.com/video/BV1xx411c7mD"]


def test_batch_txt_splits_many_links_even_when_they_share_one_line(tmp_path: Path):
    from ingest2md.batch.loader import load_batch

    manifest = tmp_path / "mixed.txt"
    manifest.write_text(
        "6.15 复制打开抖音 https://v.douyin.com/first111/ 分享文字\n"
        "\n"
        "2.51 复制打开抖音 https://v.douyin.com/second22/\n"
        "后面没有人工整理 "
        "https://v.douyin.com/third333/ 一段文字 "
        "https://v.douyin.com/fourth44/ 又一段 "
        "https://example.com/article。\n",
        encoding="utf-8",
    )

    items = load_batch(manifest)
    assert [item.source for item in items] == [
        "https://v.douyin.com/first111/",
        "https://v.douyin.com/second22/",
        "https://v.douyin.com/third333/",
        "https://v.douyin.com/fourth44/",
        "https://example.com/article",
    ]
    assert [item.line_number for item in items] == [1, 3, 4, 4, 4]


def test_batch_txt_keeps_local_files_and_plain_domains_but_ignores_prose(tmp_path: Path):
    from ingest2md.batch.loader import load_batch

    local = tmp_path / "meeting.mp4"
    local.write_bytes(b"fake")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(
        "meeting.mp4\n"
        "example.com/article\n"
        "这只是一段说明文字，没有任何链接，不应该变成任务\n",
        encoding="utf-8",
    )

    items = load_batch(manifest)
    assert [item.source for item in items] == [
        str(local.resolve()),
        "example.com/article",
    ]
