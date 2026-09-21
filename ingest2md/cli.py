"""CLI entry point: single or batch content -> lightweight local Markdown corpus."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from ingest2md.batch.loader import load_batch
from ingest2md.batch.runner import BatchRunner
from ingest2md.batch.store import TaskStore
from ingest2md.config import load_settings
from ingest2md.engine import IngestionEngine, IngestionRequest
from ingest2md.extractors.base import SourceUnavailableError
from ingest2md.extractors.youtube import YouTubeExtractor
from ingest2md.media import youtube as youtube_source
from ingest2md.runtime import RuntimeContext
from ingest2md.router import (
    UnsupportedURLError, explain_route, find_extractor, format_route_explanation, normalize_reference,
)

logger = logging.getLogger("ingest2md")

EXIT_OK = 0
EXIT_FETCH_FAILED = 1
EXIT_UNSUPPORTED = 2


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
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
        description="把网页链接、App 分享文案或本地音视频转换成适合人和 LLM 阅读的本地 Markdown",
        epilog='提示：输入请用引号完整包裹，例如 ingest2md "https://www.zhihu.com/question/xxx"',
    )
    parser.add_argument("source", help="URL、App 分享文案、本地音视频路径或 B站 BV 号")
    _add_runtime_arguments(parser)
    parser.add_argument("--explain", action="store_true",
                        help="只解释来源识别、Adapter 和处理计划，不抓取或生成文件")
    parser.add_argument("--check-access", action="store_true",
                        help="仅检测 YouTube 元数据/音轨/Cookie/JS Runtime")
    return parser


def build_batch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest2md batch",
        description="批量处理 TXT / JSONL / CSV 中的内容引用，并用 SQLite 保存可恢复状态",
    )
    parser.add_argument("manifest", help="批量任务文件：.txt 自由粘贴文本 / .jsonl / .csv")
    _add_runtime_arguments(parser)
    parser.add_argument("--resume", action="store_true",
                        help="沿用 SQLite 状态；成功任务自动跳过，中断中的任务恢复为 pending")
    parser.add_argument("--take", type=int, default=0, help="本次最多处理 N 个 pending 任务；0 为全部")
    parser.add_argument("--retry-failed", action="store_true", help="把本批次 failed 任务重新置为 pending")
    parser.add_argument("--state-db", help="SQLite 状态库路径；默认 <output>/.ingest2md-batch.sqlite3")
    return parser


def _settings_from_args(args):
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


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )


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
        settings = _settings_from_args(args)
        reference = normalize_reference(args.source)

        if args.check_access:
            extractor = find_extractor(reference, settings=settings)
            if not isinstance(extractor, YouTubeExtractor):
                raise ValueError("--check-access 当前仅用于 YouTube 链接")
            cookies_file = settings.youtube_cookies_file or settings.cookies_file
            report = youtube_source.check_access(reference, cookies_file)
            print(youtube_source.format_access_report(report))
            return EXIT_OK if report["ok"] else EXIT_FETCH_FAILED

        result, output_dir = asyncio.run(_run_single_ingestion(settings, args.source))
    except SourceUnavailableError as exc:
        print(exc, file=sys.stderr)
        return EXIT_UNSUPPORTED
    except UnsupportedURLError as exc:
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

    print(f"识别为 {result.source_name}，输出目录: {output_dir}")
    print(f"已保存: {result.output_path}")
    if result.document.image_map:
        print(f"已下载 {len(result.document.image_map)} 张图片到本地")
    return EXIT_OK


async def _run_single_ingestion(settings, source: str):
    async with RuntimeContext(settings) as runtime:
        engine = IngestionEngine(settings, runtime=runtime)
        result = await engine.ingest_one(IngestionRequest(source))
        return result, engine.output_dir


async def _run_batch(args) -> int:
    settings = _settings_from_args(args)
    if args.take < 0:
        raise ValueError("--take 必须是非负整数")

    items = load_batch(args.manifest)
    async with RuntimeContext(settings) as runtime:
        engine = IngestionEngine(settings, runtime=runtime)
        state_db = (
            Path(args.state_db).expanduser().resolve()
            if args.state_db
            else engine.output_dir / ".ingest2md-batch.sqlite3"
        )
        store = TaskStore(state_db)
        try:
            runner = BatchRunner(engine, store)
            summary = await runner.run(
                items,
                resume=args.resume,
                take=args.take,
                retry_failed=args.retry_failed,
            )
        finally:
            store.close()

    print(
        f"批量完成: 总任务 {summary.total} | 成功 {summary.success} | "
        f"失败 {summary.failed} | 待处理 {summary.pending}"
    )
    print(f"状态库: {state_db}")
    return EXIT_OK if summary.failed == 0 else EXIT_FETCH_FAILED


def batch_main(argv: list[str]) -> int:
    args = build_batch_parser().parse_args(argv)
    _configure_logging(args.verbose)
    try:
        return asyncio.run(_run_batch(args))
    except (ValueError, FileNotFoundError) as exc:
        logger.error("批量任务配置错误: %s", exc)
        return EXIT_FETCH_FAILED
    except Exception as exc:
        logger.error("批量执行失败: %s", exc)
        if args.verbose:
            raise
        return EXIT_FETCH_FAILED


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "batch":
        return batch_main(args[1:])
    return single_main(args)


if __name__ == "__main__":
    sys.exit(main())
