"""Safe extraction of readable evidence from search-result pages."""

from __future__ import annotations

import concurrent.futures
import re
from html.parser import HTMLParser

from infrastructure.tools.http_client import download_url

MAX_PAGE_BYTES = 2 * 1024 * 1024
_SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "form", "nav", "footer"}
_BLOCK_TAGS = {"article", "blockquote", "br", "div", "h1", "h2", "h3", "h4", "li", "main", "p", "section", "td", "tr"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        lowered = tag.lower()
        if lowered in _SKIP_TAGS:
            self._skip_depth += 1
        elif not self._skip_depth and lowered in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif not self._skip_depth and lowered in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.parts.append(data)


def _decode(data: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type or "", flags=re.I)
    encodings = [match.group(1)] if match else []
    encodings.extend(["utf-8", "gb18030", "latin-1"])
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _clean(text: str, limit: int) -> str:
    lines = []
    for line in text.replace("\x00", " ").splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        if normalized:
            lines.append(normalized)
    output = "\n".join(lines)
    return output[:limit].strip()


def fetch_page_text(url: str, *, timeout: int = 10, limit: int = 5000) -> str:
    resource = download_url(
        url,
        max_bytes=MAX_PAGE_BYTES,
        timeout=max(3, min(20, int(timeout))),
        user_agent="Mozilla/5.0 (compatible; Telegram-AI-Bot/1.0; search evidence fetcher)",
    )
    media_type = resource.content_type.split(";", 1)[0].strip().lower()
    if media_type and media_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
        return ""
    decoded = _decode(resource.data, resource.content_type)
    if media_type in {"text/html", "application/xhtml+xml"} or "<html" in decoded[:500].lower():
        parser = _TextExtractor()
        parser.feed(decoded)
        decoded = "".join(parser.parts)
    return _clean(decoded, limit)


def enrich_results(results: list[dict], *, top_n: int, timeout: int, content_limit: int) -> dict:
    candidates = [item for item in results[:max(0, top_n)] if not item.get("content") and item.get("url")]
    if not candidates:
        return {"attempted": 0, "fetched": 0, "failed": 0}

    def fetch(item: dict) -> tuple[dict, str]:
        try:
            return item, fetch_page_text(item["url"], timeout=timeout, limit=content_limit)
        except Exception:
            return item, ""

    fetched = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(candidates))) as executor:
        for item, content in executor.map(fetch, candidates):
            if content:
                item["content"] = content
                item["content_source"] = "page"
                fetched += 1
    return {"attempted": len(candidates), "fetched": fetched, "failed": len(candidates) - fetched}
