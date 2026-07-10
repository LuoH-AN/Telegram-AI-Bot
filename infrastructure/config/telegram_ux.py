"""Telegram interaction settings."""

from __future__ import annotations

DEFAULT_TELEGRAM_BUSY_MODE = "interrupt"
DEFAULT_TELEGRAM_TOOL_PROGRESS = "compact"

VALID_TELEGRAM_BUSY_MODES = frozenset({"interrupt", "queue"})
VALID_TELEGRAM_TOOL_PROGRESS = frozenset({"off", "compact", "full"})


def normalize_telegram_busy_mode(value: str | None, *, default: str = DEFAULT_TELEGRAM_BUSY_MODE) -> str:
    current = (value or "").strip().lower()
    return current if current in VALID_TELEGRAM_BUSY_MODES else default


def normalize_telegram_tool_progress(
    value: str | None,
    *,
    default: str = DEFAULT_TELEGRAM_TOOL_PROGRESS,
) -> str:
    current = (value or "").strip().lower()
    return current if current in VALID_TELEGRAM_TOOL_PROGRESS else default
