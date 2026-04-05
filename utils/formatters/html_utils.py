"""Utility helpers for HTML parsing."""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin


def resolve_url(url: str, base_url: str) -> str:
    if not url:
        return url
    if url.startswith(("http://", "https://", "mailto:", "tel:", "#", "data:")):
        return url
    return urljoin(base_url, url) if base_url else url


def get_attr(tag: str, attr: str) -> str:
    pattern = rf'{attr}\s*=\s*["\']([^"\']*)["\']'
    match = re.search(pattern, tag, re.IGNORECASE)
    return match.group(1) if match else ""


def process_text(text: str, *, in_pre: bool) -> str:
    text = html.unescape(text)
    if in_pre:
        return text
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n", "\n\n", text)
