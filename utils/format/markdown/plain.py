"""Strip markdown formatting for platforms that don't render MD (e.g. QQ)."""

from __future__ import annotations

import re

_CODE_FENCE_RE = re.compile(r"```(?:[^\n`]*)?\n?(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_AUTOLINK_RE = re.compile(r"<((?:https?|ftp)://[^>\s]+)>")
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^[ \t]{0,3}>+[ \t]?", re.MULTILINE)
_HR_RE = re.compile(r"^[ \t]{0,3}(?:[-*_][ \t]?){3,}[ \t]*$", re.MULTILINE)
_LIST_RE = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])[ \t]+", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?(?:[ \t]*\|[ \t]*:?-{2,}:?)+[ \t]*\|?[ \t]*$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^[ \t]*\|(.*)\|[ \t]*$", re.MULTILINE)
_BOLD_ITAL_RE = re.compile(r"(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
_STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.DOTALL)
_SPOILER_RE = re.compile(r"\|\|(?=\S)(.+?)(?<=\S)\|\|", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"</?(?:b|strong|i|em|u|s|del|code|pre|br|p|span|div)\b[^>]*>", re.IGNORECASE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def _strip_table_row(match: re.Match[str]) -> str:
    cells = [cell.strip() for cell in match.group(1).split("|")]
    return " | ".join(cell for cell in cells if cell)


def markdown_to_plain(text: str) -> str:
    """Convert Markdown text into plain text suitable for QQ/OneBot."""
    if not text:
        return ""

    cleaned = _THINK_RE.sub("", text)
    cleaned = _CODE_FENCE_RE.sub(lambda m: m.group(1).strip("\n"), cleaned)
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _IMAGE_RE.sub(r"\1", cleaned)
    cleaned = _LINK_RE.sub(lambda m: m.group(1) if m.group(1).strip() else m.group(2), cleaned)
    cleaned = _AUTOLINK_RE.sub(r"\1", cleaned)
    cleaned = _HR_RE.sub("", cleaned)
    cleaned = _TABLE_SEP_RE.sub("", cleaned)
    cleaned = _TABLE_ROW_RE.sub(_strip_table_row, cleaned)
    cleaned = _HEADING_RE.sub("", cleaned)
    cleaned = _BLOCKQUOTE_RE.sub("", cleaned)
    cleaned = _LIST_RE.sub(r"\1", cleaned)
    for _ in range(3):
        new_cleaned = _BOLD_ITAL_RE.sub(r"\2", cleaned)
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned
    cleaned = _STRIKE_RE.sub(r"\1", cleaned)
    cleaned = _SPOILER_RE.sub(r"\1", cleaned)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = cleaned.replace("\\*", "*").replace("\\_", "_").replace("\\`", "`")
    cleaned = cleaned.replace("\\[", "[").replace("\\]", "]").replace("\\#", "#")
    cleaned = _MULTI_BLANK_RE.sub("\n\n", cleaned)
    return cleaned.strip()
