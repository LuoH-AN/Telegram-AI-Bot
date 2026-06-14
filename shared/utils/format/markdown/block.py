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
    expandable = False

    def _flush() -> None:
        nonlocal expandable
        if quote_lines:
            if quote_lines[-1].rstrip().endswith("||"):
                quote_lines[-1] = quote_lines[-1].rstrip()[:-2].rstrip()
                expandable = True
            start, end = ("\x02BQXSTART\x02", "\x02BQXEND\x02") if expandable else ("\x02BQSTART\x02", "\x02BQEND\x02")
            out.append(start + "\n".join(quote_lines) + end)
            quote_lines.clear()
            expandable = False

    for line in lines:
        match = re.match(r'^>(!?)\s?(.*)', line)
        if match:
            expandable = expandable or bool(match.group(1))
            quote_lines.append(match.group(2))
        else:
            _flush()
            out.append(line)
    _flush()
    return '\n'.join(out)
