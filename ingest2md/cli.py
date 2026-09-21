"""CLI entry point: single ingestion plus resumable platform-neutral batch mode."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from ingest2md.batch.loader import load_batch_file
from ingest2md.batch.runner import BatchRunner
from ingest2md.batch.store import TaskStore
from ingest2md.config import load_settings
from ingest2md.engine import IngestionEngine, IngestionRequest, config_fingerprint
from ingest2md.extractors.youtube import YouTubeExtractor
from ingest2md.media import youtube as youtube_source
from ingest2md.router import (
    UnsupportedURLError, explain_route, find_extractor, format_route_explanation,
    normalize_reference,
)
from ingest2md.runtime import RuntimeContext

logger = logging.getLogger("ingest2md")

EXIT_OK = 0
EXIT_FETCH_FAILED = 1
EXIT_UNSUPPORTED = 2


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-o", "--output", "--output-dir", default=None,
                        help="输出根目录（默认 ./output）")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--config", help="配置文件路径（默认读取当前目录 config.yaml）")

    parser.add_argument("--asr-backend", choices=["sensevoice", "openai", "llm"],
                        help="ASR 后端；默认 sensevoice 本地转写")
    parser.add_argument("--asr-language", help="ASR 语言；默认 auto")
    parser.add_argument("--limit-seconds", type=int, help="仅处理前 N 秒；0 为全片")
    parser.add_argument("--sensevoice-model-dir", help="本地 SenseVoiceSmall 模型目录；为空时首次使用自动下载")
    parser.add_argument("--sensevoice-chunk-seconds", type=int, help="SenseVoice WAV 切片秒数（5–30，默认 30）")
    parser.add_argument("--sensevoice-batch-size", type=int, help="SenseVoice 批量推理大小（默认 2；性能和内存充足时可尝试 4）")
    parser.add_argument("--openai-asr-base-url", help="OpenAI-compatible ASR API base URL")
    parser.add_argument("--openai-asr-api-key", help="OpenAI-compatible ASR API Key")
    parser.add_argument("--openai-asr-model", help="OpenAI-compatible ASR 模型")
    parser.add_argument("--llm-base-url", help="多模态 LLM API base URL")
    parser.add_argument("--llm-api-key", help="多模态 LLM API Key")
    parser.add_argument("--llm-model", "--model", dest="llm_model", help="多模态 LLM 音频转写模型")
    parser.add_argument("--llm-api", choices=["chat", "responses"], help="多模态 LLM API 类型")
    parser.add_argument("--keep-audio", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--keep-chunks", action=argparse.BooleanOptionalAction, default=None)

    parser.add_argument("--cookies-file", help="通用 Netscape Cookie 文件（各站专用参数优先）")
    parser.add_argument("--youtube-cookies-file", help="YouTube 专用 Netscape Cookie 文件")
    parser.add_argument("--bilibili-cookies-file", help="B站专用 Netscape Cookie 文件")
    parser.add_argument("--zhihu-cookies-file", help="知乎专用 Netscape Cookie 文件")
    parser.add_argument("--xiaohongshu-cookies-file", help="小红书专用 Netscape Cookie 文件")
    parser.add_argument("--douyin-cookies-file", help="抖音专用 Netscape Cookie 文件（可选）")

    parser.add_argument("--max-answers", type=int,
                        help="知乎最多抓取 N 个回答；0/不设置表示尽可能多")
    parser.add_argument(
        "--formats",
        help="默认仅 md；需要额外产物时显式指定，如 md,srt 或 md,json（支持 md,txt,srt,json）",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest2md",
        description="把网页链接、App 分享文案或本地内容转换成适合人和 LLM 阅读的 Markdown",
        epilog=(
            '单条：ingest2md "https://example.com"；'
            '批量：ingest2md batch sources.txt --resume'
        ),
    )
    parser.add_argument("source", help="URL、App 分享文案、本地文件路径或 B站 BV 号")
    parser.add_argument("--explain", action="store_true",
                        help="只解释来源识别、Adapter 和处理计划，不抓取或生成文件")
    parser.add_argument("--check-access", action="store_true",
                        help="仅检测 YouTube 元数据/音轨/Cookie/JS Runtime")
    _add_runtime_options(parser)
    return parser


def build_batch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest2md batch",
        description="批量处理 TXT / JSONL / CSV 中的 Content Reference",
    )
    parser.add_argument("manifest", help="TXT / JSONL / CSV 批量任务文件")
    parser.add_argument("--resume", action="store_true",
                        help="保留已成功/失败状态，仅继续 pending/中断任务")
    parser.add_argument("--retry-failed", action="store_true",
                        help="本次只重试 failed 任务")
    parser.add_argument("--take", type=int, default=0,
                        help="本次最多处理 N 个选中任务；0 表示全部")
    parser.add_argument("--status", action="store_true",
                        help="只显示当前 manifest + 配置指纹的任务状态，不执行")
    _add_runtime_options(parser)
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )


def _load_settings_from_args(args):
    return load_settings(
        args.config,
        output_dir=args.output,
        asr_backend=args.asr_backend,
        asr_language=args.asr_language,
        limit_seconds=args.limit_seconds,
        sensevoice_model_dir=args.sensevoice_model_dir,
        sensevoice_chunk_seconds=args.sensevoice_chunk_seconds,
        sensevoice_batch_size=args.sensevoice_batch_size,
        openai_asr_base_url=args.openai_asr_base_url,
        openai_asr_api_key=args.openai_asr_api_key,
        openai_asr_model=args.openai_asr_model,
        llm_base_url=args.llm_base_url,
        llm_api_key=args.llm_api_key,
        llm_model=args.llm_model,
        llm_api=args.llm_api,
        cookies_file=args.cookies_file,
        youtube_cookies_file=args.youtube_cookies_file,
        bilibili_cookies_file=args.bilibili_cookies_file,
        zhihu_cookies_file=args.zhihu_cookies_file,
        xiaohongshu_cookies_file=args.xiaohongshu_cookies_file,
        douyin_cookies_file=args.douyin_cookies_file,
        max_answers=args.max_answers,
        formats=args.formats,
        keep_audio=args.keep_audio,
        keep_chunks=args.keep_chunks,
    )


async def _run_single(args, settings):
    output_dir = Path(settings.output_dir).expanduser().resolve()
    async with RuntimeContext(settings, output_dir) as runtime:
        engine = IngestionEngine(settings, output_dir, runtime=runtime)
        return await engine.ingest_one(IngestionRequest(source=args.source))


def single_main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)

    if args.explain:
        try:
            print(format_route_explanation(explain_route(args.source)))
            return EXIT_OK
        except UnsupportedURLError as exc:
            print(exc, file=sys.stderr)
            return EXIT_UNSUPPORTED

    try:
        settings = _load_settings_from_args(args)
        reference = normalize_reference(args.source)
        extractor = find_extractor(reference, settings=settings)
        if args.check_access:
            if not isinstance(extractor, YouTubeExtractor):
                raise ValueError("--check-access 当前仅用于 YouTube 链接")
            cookies_file = settings.youtube_cookies_file or settings.cookies_file
            report = youtube_source.check_access(reference, cookies_file)
            print(youtube_source.format_access_report(report))
            return EXIT_OK if report["ok"] else EXIT_FETCH_FAILED

        output_dir = Path(settings.output_dir).expanduser().resolve()
        print(f"识别为 {extractor.name}，输出目录: {output_dir}")
        result = asyncio.run(_run_single(args, settings))
    except UnsupportedURLError as exc:
        print(exc, file=sys.stderr)
        return EXIT_UNSUPPORTED
    except Exception as exc:
        logger.error("抓取/转换失败: %s", exc)
        if args.verbose:
            raise
        return EXIT_FETCH_FAILED

    if result.status != "success":
        if result.error_code == "unsupported":
            print(result.error_message, file=sys.stderr)
            return EXIT_UNSUPPORTED
        logger.error("抓取/转换失败: %s", result.error_message)
        if args.verbose and result.exception is not None:
            raise result.exception
        return EXIT_FETCH_FAILED

    print(f"已保存: {result.output_path}")
    if result.document and result.document.image_map:
        print(f"已下载 {len(result.document.image_map)} 张图片到本地")
    return EXIT_OK


def _format_summary(summary: dict[str, int]) -> str:
    return (
        f"总任务: {summary.get('total', 0)} | "
        f"成功: {summary.get('success', 0)} | "
        f"待处理: {summary.get('pending', 0)} | "
        f"运行中: {summary.get('running', 0)} | "
        f"失败: {summary.get('failed', 0)} | "
        f"跳过: {summary.get('skipped', 0)}"
    )


async def _run_batch(args, settings, requests, store, batch_key, fingerprint):
    output_dir = Path(settings.output_dir).expanduser().resolve()
    async with RuntimeContext(settings, output_dir) as runtime:
        engine = IngestionEngine(settings, output_dir, runtime=runtime)
        runner = BatchRunner(engine, store, batch_key, fingerprint)
        return await runner.run(
            requests,
            resume=args.resume,
            retry_failed=args.retry_failed,
            take=args.take,
        )


def batch_main(argv: list[str]) -> int:
    args = build_batch_parser().parse_args(argv)
    _configure_logging(args.verbose)
    if args.take < 0:
        print("--take 不能为负数", file=sys.stderr)
        return EXIT_FETCH_FAILED

    try:
        settings = _load_settings_from_args(args)
        output_dir = Path(settings.output_dir).expanduser().resolve()
        manifest = Path(args.manifest).expanduser().resolve()
        batch_key = str(manifest)
        fingerprint = config_fingerprint(settings)
        store = TaskStore(output_dir / ".ingest2md" / "batch.db")
        try:
            if args.status:
                print(_format_summary(store.summary(batch_key, fingerprint)))
                return EXIT_OK

            requests = load_batch_file(manifest)
            summary = asyncio.run(_run_batch(
                args, settings, requests, store, batch_key, fingerprint,
            ))
        finally:
            store.close()
    except Exception as exc:
        logger.error("批量处理失败: %s", exc)
        if args.verbose:
            raise
        return EXIT_FETCH_FAILED

    print(_format_summary(summary))
    return EXIT_FETCH_FAILED if summary.get("failed", 0) else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "batch":
        return batch_main(args[1:])
    return single_main(args)


if __name__ == "__main__":
    sys.exit(main())
