"""Helpers for detecting provider rate-limit errors and retry delay."""

from __future__ import annotations

import re

_RESET_PATTERNS = (
    re.compile(r"reset in\s+(\d+(?:\.\d+)?)s", re.IGNORECASE),
    re.compile(r"retry[_\s-]*after[=:]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
)


def rate_limit_retry_delay_seconds(exc: Exception) -> float | None:
    text = str(exc or "").strip()
    lower = text.lower()
    if not text:
        return None
    if "429" not in lower and "too many requests" not in lower and "rate limit" not in lower:
        return None
    for pattern in _RESET_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                value = float(match.group(1))
                if value > 0:
                    return value
            except Exception:
                continue
    return 2.0

