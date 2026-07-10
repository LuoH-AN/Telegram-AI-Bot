"""User-timezone helpers and human-readable cron previews."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .matcher import _cron_matches

DEFAULT_TIMEZONE = "Asia/Shanghai"
_WEEKDAYS = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
}
_WEEKDAYS_ZH = {
    0: "周日",
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
}


def safe_timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((name or DEFAULT_TIMEZONE).strip())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def next_run_at(expr: str, timezone_name: str, *, start: datetime | None = None, horizon_days: int = 32) -> datetime | None:
    tz = safe_timezone(timezone_name)
    current = (start.astimezone(tz) if start else datetime.now(tz)).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(max(1, horizon_days) * 24 * 60):
        if _cron_matches(expr, current):
            return current
        current += timedelta(minutes=1)
    return None


def describe_cron(expr: str, *, lang: str = "en") -> str:
    parts = (expr or "").split()
    if len(parts) != 5:
        return expr
    minute, hour, day, month, weekday = parts
    zh = lang.startswith("zh")
    if day == month == weekday == "*" and minute.isdigit() and hour.isdigit():
        return f"每天 {int(hour):02d}:{int(minute):02d}" if zh else f"Every day at {int(hour):02d}:{int(minute):02d}"
    if day == month == "*" and minute.isdigit() and hour.isdigit() and weekday.isdigit():
        weekday_number = int(weekday)
        if zh:
            return f"每{_WEEKDAYS_ZH.get(weekday_number, weekday)} {int(hour):02d}:{int(minute):02d}"
        return f"Every {_WEEKDAYS.get(weekday_number, weekday)} at {int(hour):02d}:{int(minute):02d}"
    if hour == day == month == weekday == "*" and minute.startswith("*/") and minute[2:].isdigit():
        value = int(minute[2:])
        return f"每 {value} 分钟" if zh else f"Every {value} minutes"
    return f"Cron: {expr}"
