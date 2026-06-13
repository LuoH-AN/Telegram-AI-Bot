"""Plugin registry event callback helpers."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Callable

logger = logging.getLogger(__name__)
ToolEventCallback = Callable[[dict[str, Any]], None]
TOOL_EVENT_CALLBACK: ContextVar[ToolEventCallback | None] = ContextVar("tool_event_callback", default=None)


def set_event_callback(callback: ToolEventCallback | None):
    return TOOL_EVENT_CALLBACK.set(callback) if callback else None


def reset_event_callback(token) -> None:
    if token is not None:
        TOOL_EVENT_CALLBACK.reset(token)


def emit_tool_progress(message: str, *, tool_name: str | None = None, stage: str = "progress", **extra) -> None:
    callback = TOOL_EVENT_CALLBACK.get()
    if callback is None:
        return
    event: dict[str, Any] = {"type": "tool_progress", "stage": stage, "message": str(message or "").strip()}
    if tool_name:
        event["tool_name"] = tool_name
    if extra:
        event.update(extra)
    try:
        callback(event)
    except Exception:
        logger.debug("tool progress callback failed", exc_info=True)


def emit_batch_event(callback: ToolEventCallback | None, user_id: int, event_type: str, **payload) -> None:
    if callback is None:
        return
    event = {"type": event_type, "user_id": user_id}
    event.update(payload)
    try:
        callback(event)
    except Exception:
        logger.debug("tool event callback failed (type=%s)", event_type, exc_info=True)
