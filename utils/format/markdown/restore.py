"""Restore placeholders after markdown-to-HTML conversion."""

from __future__ import annotations

import html


def restore_markdown_placeholders(
    text: str,
    *,
    code_blocks: list[str],
    inline_codes: list[str],
    tables: list[str],
    headings: list[str],
    spoilers: list[str],
) -> str:
    for index, code in enumerate(code_blocks):
        text = text.replace(f"\x02CODEBLOCK{index}\x02", f"<pre>{html.escape(code)}</pre>")
    for index, code in enumerate(inline_codes):
        text = text.replace(f"\x02INLINECODE{index}\x02", f"<code>{html.escape(code)}</code>")
    for index, table_html in enumerate(tables):
        text = text.replace(f"\x02TABLE{index}\x02", table_html)
    for index, heading in enumerate(headings):
        text = text.replace(f"\x02HEADING{index}\x02", f"<b>{html.escape(heading)}</b>")
    text = text.replace('\x02BQSTART\x02', '<blockquote>')
    text = text.replace('\x02BQEND\x02', '</blockquote>')
    text = text.replace('\x02BQXSTART\x02', '<blockquote expandable>')
    text = text.replace('\x02BQXEND\x02', '</blockquote>')
    for index, spoiler in enumerate(spoilers):
        text = text.replace(f"\x02SPOILER{index}\x02", f"<tg-spoiler>{html.escape(spoiler)}</tg-spoiler>")
    return text
