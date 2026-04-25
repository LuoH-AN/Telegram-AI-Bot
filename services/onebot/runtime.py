"""Shared registry for the active OneBot runtime."""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable


@runtime_checkable
class OneBotRuntimeLike(Protocol):
    client: "OneBotClient"

    def get_login_snapshot(self) -> dict:
        ...


_runtime: OneBotRuntimeLike | None = None
_lock = threading.RLock()


def set_onebot_runtime(runtime: OneBotRuntimeLike | None) -> None:
    global _runtime
    with _lock:
        _runtime = runtime


def get_onebot_runtime() -> OneBotRuntimeLike | None:
    with _lock:
        return _runtime
