"""Datetime context for system prompt."""

from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=8))


def get_datetime_prompt() -> str:
    """Return current Beijing time string to append to system prompt."""
    now = datetime.now(_CST)
    return f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}, {now.strftime('%A')} (UTC+8)"
