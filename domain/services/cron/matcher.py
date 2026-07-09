"""Cron expression matching utilities."""

from __future__ import annotations

from datetime import datetime


def _cron_matches(expr: str, dt: datetime) -> bool:
    """Check if a cron expression matches the given datetime."""
    parts = expr.split()
    if len(parts) != 5:
        return False

    values = [dt.minute, dt.hour, dt.day, dt.month, dt.isoweekday() % 7]
    ranges = [
        (0, 59),  # minute
        (0, 23),  # hour
        (1, 31),  # day
        (1, 12),  # month
        (0, 6),  # weekday (0=Sun)
    ]
    for field_str, current, (lo, hi) in zip(parts, values, ranges):
        if not _field_matches(field_str, current, lo, hi):
            return False
    return True


def _field_matches(field: str, value: int, lo: int, hi: int) -> bool:
    """Check if a single cron field matches the given value.

    Supports: *, exact N, a-b ranges, and /step on any base (incl. single value
    like 5/2 = 5,7,9...). Ranges are clamped to [lo, hi]; out-of-range single
    values simply never match.
    """
    if value < lo or value > hi:
        return False
    for item in field.split(","):
        item = item.strip()
        if not item:
            continue

        step = 1
        if "/" in item:
            base, step_str = item.split("/", 1)
            try:
                step = int(step_str)
            except ValueError:
                continue
            if step <= 0:
                continue
            item = base

        if item == "*":
            if (value - lo) % step == 0:
                return True
        elif "-" in item:
            try:
                start, end = item.split("-", 1)
                start, end = int(start), int(end)
            except ValueError:
                continue
            start = max(lo, start)
            end = min(hi, end)
            if start <= value <= end and (value - start) % step == 0:
                return True
        else:
            try:
                base = int(item)
            except ValueError:
                continue
            if base < lo:
                continue
            if step == 1:
                if base == value:
                    return True
            elif value >= base and (value - base) % step == 0:
                return True

    return False
