"""Datetime context for system prompt."""

from datetime import datetime, timezone


def get_datetime_prompt() -> str:
    """Return current datetime string to append to system prompt."""
    now = datetime.now(timezone.utc)
    return f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}, {now.strftime('%A')}"
