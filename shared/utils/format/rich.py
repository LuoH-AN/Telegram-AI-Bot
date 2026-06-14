"""Telegram rich message formatting helpers."""

from __future__ import annotations

import re

MAX_RICH_MESSAGE_LENGTH = 32768

_RICH_MARKERS = (
    "\n# ",
    "\n## ",
    "\n|",
    "\n- [",
    "\n* [",
    "$$",
    "```math",
    "[^",
    "<details",
    "<table",
    "<tg-",
)


def markdown_to_telegram_rich_markdown(text: str) -> str:
    if not text:
        return ""
    text = _convert_thinking_block(text)
    text = _convert_quote_tokens(text, "\x02BQSTART\x02", "\x02BQEND\x02")
    text = _convert_details_tokens(text)
    return text.replace("\x02BQXSTART\x02", "").replace("\x02BQXEND\x02", "")


def should_use_rich_message(text: str) -> bool:
    prepared = markdown_to_telegram_rich_markdown(text)
    if not prepared or len(prepared) > MAX_RICH_MESSAGE_LENGTH:
        return False
    if len(prepared) > 3500:
        return True
    return any(marker in f"\n{prepared}" for marker in _RICH_MARKERS)


def build_rich_message(text: str) -> dict | None:
    prepared = markdown_to_telegram_rich_markdown(text)
    if not prepared or len(prepared) > MAX_RICH_MESSAGE_LENGTH:
        return None
    return {"markdown": prepared}


def _convert_thinking_block(text: str) -> str:
    pattern = re.compile(r"\*\*(Thoughts(?: \(\d+s\))?)\*\*\n\x02BQXSTART\x02(.*?)\x02BQXEND\x02\n\n", re.DOTALL)

    def _replace(match: re.Match) -> str:
        title = match.group(1)
        body = match.group(2).strip()
        return f"<details><summary>{title}</summary>\n\n{body}\n\n</details>\n\n"

    return pattern.sub(_replace, text)


def _convert_quote_tokens(text: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r"(.*?)" + re.escape(end), re.DOTALL)

    def _replace(match: re.Match) -> str:
        body = match.group(1).strip("\n")
        return "\n".join(f"> {line}" if line else ">" for line in body.splitlines())

    return pattern.sub(_replace, text)


def _convert_details_tokens(text: str) -> str:
    pattern = re.compile(r"\x02BQXSTART\x02(.*?)\x02BQXEND\x02", re.DOTALL)

    def _replace(match: re.Match) -> str:
        body = match.group(1).strip()
        return f"<details><summary>Details</summary>\n\n{body}\n\n</details>"

    return pattern.sub(_replace, text)
