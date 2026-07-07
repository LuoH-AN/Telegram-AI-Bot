"""Tool event callback plumbing (progress + batch lifecycle)."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Callable

logger = logging.getLogger(__name__)
EventCallback = Callable[[dict[str, Any]], None]
_CALLBACK: ContextVar[EventCallback | None] = ContextVar("tool_event_callback", default=None)


def bind_callback(callback: EventCallback | None):
    return _CALLBACK.set(callback) if callback else None


def release_callback(token) -> None:
    if token is not None:
        _CALLBACK.reset(token)


def emit_progress(message: str, *, tool_name: str | None = None, **extra: Any) -> None:
    callback = _CALLBACK.get()
    if callback is None:
        return
    event: dict[str, Any] = {"type": "tool_progress", "stage": "progress", "message": str(message or "").strip()}
    if tool_name:
        event["tool_name"] = tool_name
    event.update(extra)
    try:
        callback(event)
    except Exception:
        logger.debug("tool progress callback failed", exc_info=True)


def emit(callback: EventCallback | None, user_id: int, event_type: str, **payload: Any) -> None:
    if callback is None:
        return
    event = {"type": event_type, "user_id": user_id}
    event.update(payload)
    try:
        callback(event)
    except Exception:
        logger.debug("tool event callback failed (type=%s)", event_type, exc_info=True)
