"""Block-level markdown transforms for Telegram HTML."""

from __future__ import annotations

import re


def transform_markdown_blocks(text: str) -> str:
    text = re.sub(r'^[-*_]{3,}\s*$', '──────────', text, flags=re.MULTILINE)
    text = re.sub(r'^([ \t]*)[-*+]\s+', r'\1• ', text, flags=re.MULTILINE)
    text = re.sub(r'^([ \t]*)(\d+)\.\s+', r'\1\2. ', text, flags=re.MULTILINE)
    return _convert_blockquotes(text)


def _convert_blockquotes(text: str) -> str:
    lines = text.split('\n')
    out: list[str] = []
    quote_lines: list[str] = []

    def _flush() -> None:
        if quote_lines:
            out.append("\x02BQSTART\x02" + "\n".join(quote_lines) + "\x02BQEND\x02")
            quote_lines.clear()

    for line in lines:
        match = re.match(r'^>\s?(.*)', line)
        if match:
            quote_lines.append(match.group(1))
        else:
            _flush()
            out.append(line)
    _flush()
    return '\n'.join(out)
