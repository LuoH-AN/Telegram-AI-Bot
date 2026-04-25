"""Markdown table conversion helpers."""

from __future__ import annotations

import html
import re


def format_cell(cell: str) -> str:
    codes = []

    def _save(match):
        codes.append(match.group(1))
        return f"\x02IC{len(codes) - 1}\x02"

    cell = re.sub(r'`([^`]+)`', _save, cell)
    cell = html.escape(cell)
    cell = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', cell)
    cell = re.sub(r'__(.+?)__', r'<b>\1</b>', cell)
    cell = re.sub(r'(?<!\w)\*([^*]+?)\*(?!\w)', r'<i>\1</i>', cell)
    cell = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', cell)
    cell = re.sub(r'~~(.+?)~~', r'<s>\1</s>', cell)
    for index, code in enumerate(codes):
        cell = cell.replace(f"\x02IC{index}\x02", f"<code>{html.escape(code)}</code>")
    return cell


def markdown_table_to_html(table_text: str) -> str:
    lines = [line.strip() for line in table_text.strip().split('\n') if line.strip()]
    if len(lines) < 3:
        return html.escape(table_text)

    def _parse_row(line: str) -> list[str]:
        text = line.strip().strip("|")
        return [cell.strip() for cell in text.split("|")]

    headers = _parse_row(lines[0])
    rows = [_parse_row(line) for line in lines[2:]]
    parts = []
    for row in rows:
        row_parts = []
        for index, cell in enumerate(row):
            header = html.escape(headers[index]) if index < len(headers) else ""
            formatted = format_cell(cell)
            row_parts.append(f"<b>{header}</b>: {formatted}" if header else formatted)
        parts.append("\n".join(row_parts))
    return "\n\n".join(parts)
