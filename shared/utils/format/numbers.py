"""Compact number formatting (k / M / B), the AI-community convention."""

from __future__ import annotations


def format_count(n: float | int, *, unit: str = "") -> str:
    """Compact a count with k/M/B suffixes.

    format_count(695618) -> "695.6K"; format_count(128000) -> "128K";
    format_count(1315672) -> "1.32M"; format_count(42) -> "42".
    Appends ``unit`` (e.g. " tokens") when given.
    """
    n = int(n) if isinstance(n, float) and n.is_integer() else n
    negative = n < 0
    value = abs(n)
    if value < 1000:
        body = f"{value}"
    elif value < 1_000_000:
        body = _compact(value / 1000, "K")
    elif value < 1_000_000_000:
        body = _compact(value / 1_000_000, "M")
    else:
        body = _compact(value / 1_000_000_000, "B")
    sign = "-" if negative else ""
    return f"{sign}{body}{unit}"


def format_tokens(n: float | int) -> str:
    """format_count with the ' tokens' unit."""
    return format_count(n, unit=" tokens")


def _compact(x: float, suffix: str) -> str:
    # Drop the decimal when the value is a whole number (128.0K -> 128K).
    if abs(x - round(x)) < 0.05:
        return f"{round(x)}{suffix}"
    return f"{x:.1f}{suffix}"
