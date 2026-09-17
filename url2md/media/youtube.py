"""YouTube single-video acquisition and access diagnostics through yt-dlp."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from shutil import which
from urllib.parse import parse_qs, urlparse


HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtube-nocookie.com", "youtube-nocookie.com",
}
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
RUNTIME_MIN_VERSIONS = {"deno": (2, 3, 0), "node": (22, 0, 0)}


class YouTubeAccessError(RuntimeError):
    """A classified YouTube acquisition failure."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def normalize_video_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in HOSTS:
        raise ValueError("不是 YouTube 视频链接")
    parts = parsed.path.strip("/").split("/")
    video_id = ""
    if host == "youtu.be":
        video_id = parts[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
        video_id = parts[1]
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("请提供单个 YouTube 视频链接（watch、youtu.be、shorts 或 embed），不支持频道/播放列表")
    return f"https://www.youtube.com/watch?v={video_id}"


def _version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text)
    if not match:
        return ()
    return tuple(int(value or 0) for value in match.groups())


def js_runtime_status() -> list[dict]:
    """Return supported-runtime diagnostics without executing any yt-dlp request."""
    statuses: list[dict] = []
    for name, minimum in RUNTIME_MIN_VERSIONS.items():
        path = which(name)
        version_text = ""
        version = ()
        if path:
            try:
                proc = subprocess.run(
                    [path, "--version"], capture_output=True, text=True,
                    timeout=5, check=False,
                )
                version_text = (proc.stdout or proc.stderr).strip().splitlines()[0]
                version = _version_tuple(version_text)
            except (OSError, subprocess.SubprocessError, IndexError):
                version_text = "无法读取版本"
        statuses.append({
            "name": name,
            "path": path or "",
            "installed": bool(path),
            "version": version_text,
            "minimum": ".".join(map(str, minimum)),
            "supported": bool(path and version and version >= minimum),
        })
    return statuses


def _selected_runtime() -> dict | None:
    return next((item for item in js_runtime_status() if item["supported"]), None)


def validate_cookie_file(cookies_file: str, domain_hint: str = "youtube") -> dict:
    """Validate the shape of a Netscape cookie file without exposing secret values."""
    if not cookies_file:
        return {
            "configured": False, "path": "", "exists": False, "valid": False,
            "cookie_count": 0, "domain_match": False,
            "message": "未配置 Cookie；将尝试匿名访问",
        }
    path = Path(cookies_file).expanduser()
    result = {
        "configured": True, "path": str(path), "exists": path.is_file(),
        "valid": False, "cookie_count": 0, "domain_match": False, "message": "",
    }
    if not path.is_file():
        result["message"] = "Cookie 文件不存在"
        return result
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        result["message"] = f"Cookie 文件无法读取: {exc}"
        return result

    domains: list[str] = []
    count = 0
    for raw in lines:
        line = raw.strip("\r\n")
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        count += 1
        domains.append(parts[0].lower())
    result["cookie_count"] = count
    result["domain_match"] = any(domain_hint in domain for domain in domains)
    result["valid"] = count > 0
    if not result["valid"]:
        result["message"] = "未发现 Netscape 格式 Cookie 记录（应为 7 列制表符分隔）"
    elif not result["domain_match"]:
        result["message"] = f"Cookie 文件格式有效，但未发现 {domain_hint} 域记录"
    else:
        result["message"] = f"Cookie 文件格式有效，共 {count} 条记录"
    return result


def _reject_live(info, *, incomplete=False):
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
        return "暂不支持直播中或尚未处理完成的视频，请使用已完成的点播视频"
    return None


def _base_options(cookies_file: str = "") -> dict:
    options = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "match_filter": _reject_live,
    }
    if cookies_file:
        cookie_status = validate_cookie_file(cookies_file)
        if not cookie_status["exists"] or not cookie_status["valid"]:
            raise ValueError(f"Cookie 文件不可用: {cookie_status['path']}；{cookie_status['message']}")
        options["cookiefile"] = str(Path(cookies_file).expanduser())
    runtime = _selected_runtime()
    if runtime:
        options["js_runtimes"] = {runtime["name"]: {"path": runtime["path"]}}
    return options


def classify_download_error(message: str) -> tuple[str, str]:
    """Map yt-dlp/YouTube failures to actionable categories."""
    lower = message.lower()
    if "sign in to confirm you're not a bot" in lower or "not a bot" in lower:
        return (
            "auth",
            "YouTube 对当前网络出口触发了 bot/登录验证。请使用从已登录浏览器导出的 YouTube Cookie；"
            "若已有 Cookie，请重新导出独立会话 Cookie 后重试。",
        )
    if "cookie" in lower and any(word in lower for word in ("expired", "invalid", "login", "sign in", "authentication")):
        return (
            "cookie",
            "YouTube Cookie 可能已失效或未包含有效登录态，请重新导出 Netscape 格式 YouTube Cookie。",
        )
    if "429" in lower or "too many requests" in lower:
        return (
            "rate_limit",
            "YouTube 返回限流（429）。请降低请求频率或更换正常网络出口；不要通过反复重导 Cookie 解决限流。",
        )
    if any(token in lower for token in ("nsig", "signature", "javascript runtime", "js challenge", "challenge solver")):
        return (
            "js",
            "YouTube JavaScript challenge 处理失败。请检查 yt-dlp/EJS 以及 Deno>=2.3 或 Node>=22，"
            "这与账号登录不是同一问题。",
        )
    if "po token" in lower or "proof of origin" in lower or "http error 403" in lower or "forbidden" in lower:
        return (
            "playback",
            "YouTube 播放请求被拒（403/PO Token 类问题）。Cookie 可能仍然有效；"
            "需要进一步检查 player client、PO Token 或网络出口。",
        )
    if "sign in" in lower or "login" in lower:
        return (
            "auth",
            "YouTube 要求登录。请提供有效的 Netscape 格式 YouTube Cookie 后重试。",
        )
    return "download", f"YouTube 请求失败: {message}"


def _raise_access_error(exc: Exception) -> None:
    kind, friendly = classify_download_error(str(exc))
    raise YouTubeAccessError(kind, friendly) from exc


def probe_video(url: str, cookies_file: str = "") -> dict:
    """Verify metadata/audio access without downloading media or consuming transcription API."""
    url = normalize_video_url(url)
    options = _base_options(cookies_file)
    options.update({"skip_download": True, "format": "bestaudio/best"})
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
    except ImportError as exc:
        raise ImportError("YouTube 通道需要 yt-dlp，请重新安装 url2md") from exc
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        _raise_access_error(exc)
    if not info or info.get("_type") in {"playlist", "multi_video"}:
        raise ValueError("未取得单个 YouTube 视频元数据")
    formats = info.get("formats") or []
    audio_formats = [fmt for fmt in formats if fmt.get("acodec") not in {None, "none"}]
    return {
        "id": info.get("id") or "",
        "title": info.get("title") or info.get("id") or "",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration") or 0,
        "url": url,
        "audio_formats": len(audio_formats),
    }


def check_access(url: str, cookies_file: str = "") -> dict:
    """Return a diagnostic report; this never downloads audio or calls transcription APIs."""
    report = {
        "url": normalize_video_url(url),
        "runtimes": js_runtime_status(),
        "cookie": validate_cookie_file(cookies_file),
        "ok": False,
        "error_kind": "",
        "error": "",
        "video": None,
    }
    try:
        report["video"] = probe_video(url, cookies_file)
        report["ok"] = True
    except YouTubeAccessError as exc:
        report["error_kind"] = exc.kind
        report["error"] = str(exc)
    except Exception as exc:
        report["error_kind"] = "config"
        report["error"] = str(exc)
    return report


def format_access_report(report: dict) -> str:
    """Human-readable diagnostics with no Cookie values."""
    lines = ["YouTube 访问检测", f"URL: {report['url']}", ""]
    supported = [item for item in report["runtimes"] if item["supported"]]
    if supported:
        item = supported[0]
        lines.append(f"✓ JavaScript Runtime: {item['name']} {item['version']}（满足最低版本 {item['minimum']}）")
    else:
        installed = [item for item in report["runtimes"] if item["installed"]]
        if installed:
            detail = ", ".join(f"{item['name']} {item['version']} < {item['minimum']}" for item in installed)
            lines.append(f"✗ JavaScript Runtime 版本过低: {detail}")
        else:
            lines.append("✗ 未找到支持的 JavaScript Runtime（推荐 Deno>=2.3；或 Node>=22）")

    cookie = report["cookie"]
    if not cookie["configured"]:
        lines.append("○ Cookie: 未配置（匿名访问）")
    elif cookie["valid"] and cookie["domain_match"]:
        lines.append(f"✓ Cookie: {cookie['path']}（格式有效，{cookie['cookie_count']} 条；不显示 Cookie 内容）")
    elif cookie["valid"]:
        lines.append(f"! Cookie: {cookie['path']}（{cookie['message']}）")
    else:
        lines.append(f"✗ Cookie: {cookie['path']}（{cookie['message']}）")

    if report["ok"]:
        video = report["video"]
        lines.extend([
            "✓ YouTube 元数据访问成功",
            f"✓ 找到可用音频格式: {video['audio_formats']} 个",
            f"视频: {video['title']}",
            f"频道: {video['uploader']}",
            f"时长: {video['duration']} 秒",
            "",
            "检测通过：未下载完整音频，也未调用转写/翻译 API。",
        ])
    else:
        lines.extend([
            f"✗ YouTube 访问失败 [{report['error_kind'] or 'unknown'}]",
            report["error"] or "未知错误",
            "",
            "检测结束：未调用转写/翻译 API。",
        ])
    return "\n".join(lines)


def download_video(url: str, work_dir: Path, cookies_file: str = "") -> tuple[dict, str]:
    url = normalize_video_url(url)
    options = _base_options(cookies_file)
    options.update({
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "audio.%(ext)s"),
    })
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
    except ImportError as exc:
        raise ImportError("YouTube 通道需要 yt-dlp，请重新安装 url2md") from exc
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info or info.get("_type") in {"playlist", "multi_video"}:
                raise ValueError("未取得单个可下载视频")
            path = Path(ydl.prepare_filename(info))
    except DownloadError as exc:
        _raise_access_error(exc)
    if not path.is_file():
        raise RuntimeError("YouTube 未产出音频文件；视频可能是直播、需要登录或无法下载")
    meta = {
        "id": info["id"],
        "title": info.get("title") or info["id"],
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration") or 0,
        "desc": info.get("description") or "",
        "url": url,
    }
    return meta, str(path)
