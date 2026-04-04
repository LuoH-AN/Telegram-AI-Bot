"""Shared registry for the active WeChat runtime."""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable


@runtime_checkable
class WeChatRuntimeLike(Protocol):
    login_access_token: str

    def get_login_snapshot(self) -> dict:
        ...

    def force_new_login_sync(self) -> dict:
        ...


_runtime: WeChatRuntimeLike | None = None
_lock = threading.RLock()


def set_wechat_runtime(runtime: WeChatRuntimeLike | None) -> None:
    global _runtime
    with _lock:
        _runtime = runtime


def get_wechat_runtime() -> WeChatRuntimeLike | None:
    with _lock:
        return _runtime
