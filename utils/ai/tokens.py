"""Shared helpers for prompt token estimation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def estimate_tokens_str(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK."""
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff" or "\u3000" <= char <= "\u30ff")
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


def estimate_tokens(messages: Sequence[Mapping[str, object]]) -> int:
    """Estimate total prompt tokens from a list of chat messages."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        total += estimate_tokens_str(str(content)) + 4
    return total
