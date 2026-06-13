"""Shared runtime state for cron scheduling."""

from __future__ import annotations

import threading
from datetime import timedelta, timezone

CST = timezone(timedelta(hours=8))
POLL_INTERVAL = 30  # seconds

running_tasks: set[tuple[int, str]] = set()
running_tasks_lock = threading.Lock()

_bot_ref = None
_main_loop = None


def get_bot_ref():
    return _bot_ref


def set_bot_ref(bot) -> None:
    global _bot_ref
    _bot_ref = bot


def get_main_loop():
    return _main_loop


def set_main_loop_ref(loop) -> None:
    global _main_loop
    _main_loop = loop
