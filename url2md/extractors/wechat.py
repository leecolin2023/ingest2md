"""WeChat official-account article channel.

Ported from jackwener/wechat-article-to-markdown, adapted to the Extractor
contract: render the page with Camoufox (anti-bot), extract metadata, convert
the article body to markdown, localize images.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from url2md.model import Document, sanitize_filename
from url2md.urlutils import host_of, normalize_url

logger = logging.getLogger(__name__)

WECHAT_HOST = "mp.weixin.qq.com"
IMAGE_CONCURRENCY = 5
UTC_PLUS_8 = timezone(timedelta(hours=8))

_CREATE_TIME_PATTERNS = [
    r"create_time\s*[:=]\s*['\"]?(\d{9,11})",
    r"createTime\s*[:=]\s*['\"]?(\d{9,11})",
    r"\bct\s*[:=]\s*['\"]?(\d{9,11})",
]

_CONVERT_TAGS = [
    "a", "blockquote", "br", "code", "del", "em", "h1", "h2", "h3", "h4",
    "h5", "h6", "hr", "img", "li", "ol", "p", "pre", "q", "s", "strong",
    "sub", "sup", "table", "tbody", "td", "th", "thead", "tr", "ul",
]


class WeChatExtractor:
    name = "微信公众号文章"
    description = "mp.weixin.qq.com 文章 → Markdown(含图片本地化、代码块转换)"

    def match(self, url: str) -> bool:
        return host_of(url) == WECHAT_HOST

    async def extract(self, url: str, output_dir: Path) -> Document:
        from camoufox.async_api import AsyncCamoufox

        url = normalize_wechat_url(url)
        logger.info("正在抓取: %s", url)

        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector("#js_content", timeout=10_000)
            except Exception:
                logger.warning("#js_content 未在 10s 内出现,继续尝试解析")
            await asyncio.sleep(2)
            html = await page.content()

        soup = BeautifulSoup(html, "html.parser")
        meta = extract_metadata(soup, html)
        if not meta["title"]:
            debug_path = output_dir / "debug.html"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(html, encoding="utf-8")
            raise RuntimeError(
                "未能提取文章标题,可能触发了验证码或页面结构变化;"
                f"原始 HTML 已保存到 {debug_path}"
            )
        logger.info("文章: %s", meta["title"])

        content_soup = soup.select_one("#js_content") or soup
        code_blocks = process_content(content_soup)
        image_urls = collect_image_urls(content_soup)

        doc_dir = output_dir / sanitize_filename(meta["title"])
        image_map = await download_all_images(image_urls, doc_dir / "images")

        body = convert_to_markdown(str(content_soup), code_blocks)
        body = replace_image_urls(body, image_map)

        metadata: list[tuple[str, str]] = []
        if meta["author"]:
            metadata.append(("公众号", meta["author"]))
        if meta["publish_time"]:
            metadata.append(("发布时间", meta["publish_time"]))

        publish_dt = None
        ts = extract_create_time(html)
        if ts:
            publish_dt = datetime.fromtimestamp(ts, tz=UTC_PLUS_8)

        return Document(
            title=meta["title"],
            source_url=url,
            metadata=metadata,
            body_md=body,
            image_map=image_map,
            publish_time=publish_dt,
        )


def normalize_wechat_url(raw: str) -> str:
    url = normalize_url(raw)
    parsed_host = host_of(url)
    if parsed_host and parsed_host != WECHAT_HOST:
        raise ValueError(f"不是微信公众号文章链接(域名 {parsed_host}): {raw}")
    return url


def extract_metadata(soup: BeautifulSoup, html: str) -> dict[str, str | None]:
    title_el = soup.select_one("#activity-name")
    author_el = soup.select_one("#js_name")
    return {
        "title": title_el.get_text(strip=True) if title_el else None,
        "author": author_el.get_text(strip=True) if author_el else None,
        "publish_time": extract_publish_time(soup, html),
    }


def extract_publish_time(soup: BeautifulSoup, html: str) -> str | None:
    el = soup.select_one("#publish_time")
    if el and el.get_text(strip=True):
        return normalize_publish_time(el.get_text(strip=True))
    ts = extract_create_time(html)
    if ts:
        return datetime.fromtimestamp(ts, tz=UTC_PLUS_8).strftime("%Y-%m-%d %H:%M:%S")
    return None


def normalize_publish_time(text: str) -> str:
    for fmt in ("%b %d, %Y, %I:%M %p", "%b %d, %Y %I:%M %p", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return text


def extract_create_time(html: str) -> int | None:
    for pattern in _CREATE_TIME_PATTERNS:
        m = re.search(pattern, html)
        if m:
            return int(m.group(1))
    return None


def process_content(content: BeautifulSoup) -> list[dict[str, str]]:
    for selector in ("script", "style", ".qr_code_pc", ".reward_area"):
        for node in content.select(selector):
            node.decompose()

    for img in content.find_all("img"):
        data_src = img.get("data-src")
        if data_src:
            img["src"] = data_src
    for img in content.find_all("img"):
        src = img.get("src") or ""
        if src.startswith("data:"):
            img.decompose()

    code_blocks: list[dict[str, str]] = []
    for snippet in content.select(".code-snippet__fix"):
        for index_el in snippet.select(".code-snippet__line-index"):
            index_el.decompose()
        pre = snippet.select_one("pre[data-lang]")
        lang = pre.get("data-lang", "") if pre else ""
        code_el = snippet.find("code")
        raw_lines = code_el.get_text("\n").split("\n") if code_el else []
        lines = [line for line in raw_lines if not re.match(r"^[ce]?ounter\(line", line.strip())]
        placeholder = f"CODEBLOCK-PLACEHOLDER-{len(code_blocks)}"
        code_blocks.append({"lang": lang, "code": "\n".join(lines).strip("\n"), "placeholder": placeholder})
        p = content.new_tag("p")
        p.string = placeholder
        snippet.replace_with(p)
    return code_blocks


def collect_image_urls(content: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    for img in content.find_all("img"):
        src = img.get("src")
        if src and src.startswith("http") and src not in urls:
            urls.append(src)
    return urls


async def download_all_images(urls: list[str], images_dir: Path) -> dict[str, str]:
    if not urls:
        return {}
    images_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(IMAGE_CONCURRENCY)
    image_map: dict[str, str] = {}
    async with httpx.AsyncClient(headers={"Referer": "https://mp.weixin.qq.com/"}, timeout=15, follow_redirects=True) as client:
        async def download(index: int, url: str) -> None:
            async with semaphore:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("图片下载失败(%s): %s", url, exc)
                    return
                ext = image_extension(url, resp)
                filename = f"img_{index:03d}.{ext}"
                (images_dir / filename).write_bytes(resp.content)
                image_map[url] = f"images/{filename}"
        await asyncio.gather(*(download(i, u) for i, u in enumerate(urls, start=1)))
    return image_map


def image_extension(url: str, resp: httpx.Response) -> str:
    m = re.search(r"wx_fmt=(\w+)", url)
    if m:
        return m.group(1).lower()
    suffix = Path(urlparse(url).path).suffix.lstrip(".")
    if suffix.isalpha() and len(suffix) <= 5:
        return suffix.lower()
    ctype = resp.headers.get("content-type", "")
    if "jpeg" in ctype or "jpg" in ctype:
        return "jpg"
    if "gif" in ctype:
        return "gif"
    if "webp" in ctype:
        return "webp"
    return "png"


def convert_to_markdown(content_html: str, code_blocks: list[dict[str, str]]) -> str:
    import markdownify
    md = markdownify.markdownify(content_html, heading_style="ATX", bullets="-", convert=_CONVERT_TAGS)
    for block in code_blocks:
        fence = f"\n```{block.get('lang', '')}\n{block['code']}\n```\n"
        md = md.replace(block["placeholder"], fence)
    md = md.replace("\u00a0", " ")
    md = re.sub(r"\n{4,}", "\n\n\n", md)
    md = re.sub(r"[ \t]+$", "", md, flags=re.MULTILINE)
    return md.strip()


def replace_image_urls(md: str, image_map: dict[str, str]) -> str:
    for remote_url, local_path in image_map.items():
        md = re.sub(re.escape(remote_url), local_path, md)
    return md
