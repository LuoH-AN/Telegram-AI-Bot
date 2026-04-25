"""Markdown to Telegram-compatible HTML conversion."""

from __future__ import annotations

import html
import re

from ..latex import latex_to_unicode
from .block import transform_markdown_blocks
from .extract import extract_markdown_placeholders
from .restore import restore_markdown_placeholders


def markdown_to_telegram_html(text: str) -> str:
    if not text:
        return text
    text = latex_to_unicode(text)
    text, code_blocks, inline_codes, tables, spoilers, headings = extract_markdown_placeholders(text)
    text = transform_markdown_blocks(text)
    text = html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*([^*]+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return restore_markdown_placeholders(
        text,
        code_blocks=code_blocks,
        inline_codes=inline_codes,
        tables=tables,
        headings=headings,
        spoilers=spoilers,
    )
