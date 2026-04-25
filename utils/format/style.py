"""HTML/style cleanup helpers."""

from __future__ import annotations

import re


def strip_style_blocks(text: str) -> str:
    """Remove embedded CSS/style blocks from HTML/Markdown text."""
    if not text:
        return ""
    cleaned = text
    cleaned = re.sub(
        r"<(?:style|script|noscript)\b[^>]*>.*?</(?:style|script|noscript)\s*>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"&lt;style\b[^&]*&gt;.*?&lt;/style&gt;",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
