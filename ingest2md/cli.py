"""CLI entry point: online content -> lightweight local Markdown corpus."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from ingest2md.config import load_settings
from ingest2md.extractors.base import SourceUnavailableError
from ingest2md.extractors.bilibili import BilibiliExtractor
from ingest2md.extractors.deferred_media import DeferredMediaExtractor
from ingest2md.extractors.local_media import LocalMediaExtractor
from ingest2md.extractors.xiaoyuzhou import XiaoyuzhouExtractor
from ingest2md.extractors.youtube import YouTubeExtractor
from ingest2md.extractors.zhihu import ZhihuExtractor
from ingest2md.extractors.xiaohongshu import XiaohongshuExtractor
from ingest2md.media import youtube as youtube_source
from ingest2md.model import write_document
from ingest2md.router import (
    UnsupportedURLError, explain_route, find_extractor, format_route_explanation, normalize_reference,
)

logger = logging.getLogger("ingest2md")

EXIT_OK = 0
EXIT_FETCH_FAILED = 1
EXIT_UNSUPPORTED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest2md",
        description=(
            "把网页链接、App 分享文案或本地音视频转换成适合人和 LLM 阅读的本地 Markdown"
        ),
        epilog='提示：输入请用引号完整包裹，例如 ingest2md "https://www.zhihu.com/question/xxx" 或 ingest2md "./podcast.m4a"',
    )
    parser.add_argument("source", help="URL、App 分享文案、本地音视频路径或 B站 BV 号")
    parser.add_argument("-o", "--output", "--output-dir", default=None,
                        help="输出根目录（默认 ./output）")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--explain", action="store_true",
                        help="只解释来源识别、Adapter 和处理计划，不抓取或生成文件")
    parser.add_argument("--config", help="配置文件路径（默认读取当前目录 config.yaml）")

    # Video options.
    parser.add_argument("--model", help="视频转写首选模型")
    parser.add_argument("--translation-model", help="中文翻译模型（默认与转写模型相同）")
    parser.add_argument("--limit-seconds", type=int, help="仅转写前 N 秒；0 为全片")
    parser.add_argument("--chunk-seconds", type=int, help="音频切段长度（默认 300 秒）")
    parser.add_argument("--check-access", action="store_true",
                        help="仅检测 YouTube 元数据/音轨/Cookie/JS Runtime")
    parser.add_argument("--keep-audio", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--keep-chunks", action=argparse.BooleanOptionalAction, default=None)

    # Cookie/session options. Netscape format keeps one export format for all sites.
    parser.add_argument("--cookies-file", help="通用 Netscape Cookie 文件（各站专用参数优先）")
    parser.add_argument("--youtube-cookies-file", help="YouTube 专用 Netscape Cookie 文件")
    parser.add_argument("--bilibili-cookies-file", help="B站专用 Netscape Cookie 文件")
    parser.add_argument("--zhihu-cookies-file", help="知乎专用 Netscape Cookie 文件")
    parser.add_argument("--xiaohongshu-cookies-file", help="小红书专用 Netscape Cookie 文件")

    parser.add_argument("--max-answers", type=int,
                        help="知乎最多抓取 N 个回答；0/不设置表示尽可能多")
    parser.add_argument(
        "--formats",
        help="默认仅 md；需要额外产物时显式指定，如 md,srt 或 md,json（支持 md,txt,srt,json）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.explain:
        try:
            print(format_route_explanation(explain_route(args.source)))
            return EXIT_OK
        except UnsupportedURLError as exc:
            print(exc, file=sys.stderr)
            return EXIT_UNSUPPORTED

    try:
        reference = normalize_reference(args.source)
        extractor = find_extractor(reference)
    except UnsupportedURLError as exc:
        print(exc, file=sys.stderr)
        return EXIT_UNSUPPORTED

    if isinstance(extractor, DeferredMediaExtractor):
        try:
            asyncio.run(extractor.extract(reference, Path(".")))
        except SourceUnavailableError as exc:
            print(exc, file=sys.stderr)
            return EXIT_UNSUPPORTED

    try:
        settings = load_settings(
            args.config,
            output_dir=args.output,
            model=args.model,
            translation_model=args.translation_model,
            limit_seconds=args.limit_seconds,
            chunk_seconds=args.chunk_seconds,
            cookies_file=args.cookies_file,
            youtube_cookies_file=args.youtube_cookies_file,
            bilibili_cookies_file=args.bilibili_cookies_file,
            zhihu_cookies_file=args.zhihu_cookies_file,
            xiaohongshu_cookies_file=args.xiaohongshu_cookies_file,
            max_answers=args.max_answers,
            formats=args.formats,
            keep_audio=args.keep_audio,
            keep_chunks=args.keep_chunks,
        )

        if args.check_access:
            if not isinstance(extractor, YouTubeExtractor):
                raise ValueError("--check-access 当前仅用于 YouTube 链接")
            cookies_file = settings.youtube_cookies_file or settings.cookies_file
            report = youtube_source.check_access(reference, cookies_file)
            print(youtube_source.format_access_report(report))
            return EXIT_OK if report["ok"] else EXIT_FETCH_FAILED

        if isinstance(extractor, (BilibiliExtractor, YouTubeExtractor, XiaoyuzhouExtractor, LocalMediaExtractor, ZhihuExtractor, XiaohongshuExtractor)):
            extractor = type(extractor)(settings)
        output_dir = Path(settings.output_dir).expanduser().resolve()
        print(f"识别为 {extractor.name}，输出目录: {output_dir}")
        doc = asyncio.run(extractor.extract(reference, output_dir))
        md_path = write_document(doc, output_dir, settings.formats)
    except SourceUnavailableError as exc:
        print(exc, file=sys.stderr)
        return EXIT_UNSUPPORTED
    except ImportError as exc:
        logger.error("缺少运行依赖，请重新安装 ingest2md: %s", exc)
        return EXIT_FETCH_FAILED
    except Exception as exc:
        logger.error("抓取/转换失败: %s", exc)
        if args.verbose:
            raise
        return EXIT_FETCH_FAILED

    print(f"已保存: {md_path}")
    if doc.image_map:
        print(f"已下载 {len(doc.image_map)} 张图片到本地")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
