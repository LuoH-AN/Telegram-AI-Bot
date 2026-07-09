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

# Platform delivery port: (chat_id, text) -> None. Injected by the adapter layer
# so domain cron never imports adapters.* directly. Returns the platform label.
_delivery_send = None
_delivery_platform = None


def get_bot_ref():
    return _bot_ref


def set_bot_ref(bot) -> None:
    global _bot_ref
    _bot_ref = bot


def get_delivery_send():
    return _delivery_send


def get_delivery_platform() -> str:
    return _delivery_platform or "this platform"


def set_delivery_port(send, platform: str) -> None:
    """Register the platform delivery callable. send(chat_id, text) -> None."""
    global _delivery_send, _delivery_platform
    _delivery_send = send
    _delivery_platform = platform


def get_main_loop():
    return _main_loop


def set_main_loop_ref(loop) -> None:
    global _main_loop
    _main_loop = loop
