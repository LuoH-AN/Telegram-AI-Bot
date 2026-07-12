"""Tool event callback plumbing (progress + batch lifecycle)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)
EventCallback = Callable[[dict[str, Any]], None]


def emit(callback: EventCallback | None, user_id: int, event_type: str, **payload: Any) -> None:
    if callback is None:
        return
    event = {"type": event_type, "user_id": user_id}
    event.update(payload)
    try:
        callback(event)
    except Exception:
        logger.debug("tool event callback failed (type=%s)", event_type, exc_info=True)
