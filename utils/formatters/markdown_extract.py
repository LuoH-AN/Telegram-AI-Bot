"""Placeholder extraction for markdown-to-Telegram conversion."""

from __future__ import annotations

import re

from .markdown_table import markdown_table_to_html


def extract_markdown_placeholders(text: str) -> tuple[str, list, list, list, list, list]:
    code_blocks: list[str] = []
    inline_codes: list[str] = []
    tables: list[str] = []
    spoilers: list[str] = []
    headings: list[str] = []

    def _save_code_block(match):
        code_blocks.append(match.group(1) or match.group(2))
        return f"\x02CODEBLOCK{len(code_blocks) - 1}\x02"

    text = re.sub(r'```(?:\w*\n)?(.*?)```|```(.*?)```', _save_code_block, text, flags=re.DOTALL)

    def _save_table(match):
        block = match.group(0)
        lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
        if len(lines) < 3:
            return block
        sep_cells = [cell.strip() for cell in lines[1].strip().strip("|").split("|")]
        if not all(re.match(r'^:?-+:?$', cell) for cell in sep_cells if cell):
            return block
        tables.append(markdown_table_to_html(block))
        return f"\x02TABLE{len(tables) - 1}\x02"

    text = re.sub(r'(?:^[ \t]*\|.+\|[ \t]*$\n?){3,}', _save_table, text, flags=re.MULTILINE)

    def _save_inline_code(match):
        inline_codes.append(match.group(1))
        return f"\x02INLINECODE{len(inline_codes) - 1}\x02"

    text = re.sub(r'`([^`]+)`', _save_inline_code, text)

    def _save_spoiler(match):
        spoilers.append(match.group(1))
        return f"\x02SPOILER{len(spoilers) - 1}\x02"

    text = re.sub(r'\|\|(.+?)\|\|', _save_spoiler, text, flags=re.DOTALL)

    def _save_heading(match):
        heading = match.group(1).strip()
        heading = re.sub(r'(\*\*|__|~~|`)', '', heading)
        heading = re.sub(r'(?<!\*)\*(?!\*)', '', heading)
        heading = re.sub(r'(?<!_)_(?!_)', '', heading)
        headings.append(heading.strip())
        return f"\x02HEADING{len(headings) - 1}\x02"

    text = re.sub(r'^#{1,6}\s+(.+)$', _save_heading, text, flags=re.MULTILINE)
    return text, code_blocks, inline_codes, tables, spoilers, headings
