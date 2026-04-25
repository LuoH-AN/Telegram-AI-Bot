"""Helpers for Telegram text chat flow."""

from __future__ import annotations

from config import VALID_REASONING_EFFORTS
from utils import extract_thinking_blocks, filter_thinking_content, format_thinking_block


def make_thinking_prefix(seconds: int | float) -> str:
    return f"_Thinking for {int(seconds)}s_\n\n" if seconds > 0 else ""


def normalize_reasoning_effort(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in VALID_REASONING_EFFORTS else ""


def append_thinking_segments(
    *,
    show_thinking: bool,
    full_response: str,
    reasoning_content: str,
    segments: list[str],
) -> None:
    if not show_thinking:
        return
    tag_thinking, _ = extract_thinking_blocks(full_response)
    for segment in (reasoning_content, tag_thinking):
        cleaned = (segment or "").strip()
        if not cleaned:
            continue
        if segments and segments[-1] == cleaned:
            continue
        segments.append(cleaned)


def build_final_display(
    *,
    final_response: str,
    fallback_response: str,
    show_thinking: bool,
    thinking_segments: list[str],
    total_thinking_seconds: float,
    thinking_max_chars: int,
) -> tuple[str, str, str]:
    final_text = filter_thinking_content(final_response).strip()
    if not final_text and fallback_response:
        final_text = filter_thinking_content(fallback_response).strip()
    if not final_text:
        final_text = "(Empty response)"

    thinking_block = ""
    if show_thinking and thinking_segments:
        thinking_text = "\n\n".join(thinking_segments).strip()
        thinking_block = format_thinking_block(
            thinking_text,
            seconds=total_thinking_seconds,
            max_chars=thinking_max_chars,
        )

    if thinking_block:
        display_final = thinking_block + final_text
    elif final_text != "(Empty response)" and total_thinking_seconds > 0:
        display_final = make_thinking_prefix(total_thinking_seconds) + final_text
    else:
        display_final = final_text
    return final_text, thinking_block, display_final
