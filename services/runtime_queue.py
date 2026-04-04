"""Per-conversation runtime serialization helpers."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

_LOCKS: dict[str, asyncio.Lock] = {}
_LOCKS_GUARD = asyncio.Lock()

# Active response tracking: slot_key -> {"task": asyncio.Task, "pump": Any}
_ACTIVE_RESPONSES: dict[str, dict] = {}


async def _get_lock(key: str) -> asyncio.Lock:
    async with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[key] = lock
        return lock


@asynccontextmanager
async def conversation_slot(key: str):
    """Serialize processing for a conversation key.

    Yields:
        queued (bool): True when another request was already running.
    """
    lock = await _get_lock(key)
    queued = lock.locked()
    await lock.acquire()
    try:
        yield queued
    finally:
        lock.release()


def register_response(key: str, *, task: asyncio.Task, pump: Any) -> None:
    """Register an active response for cancellation via /stop."""
    _ACTIVE_RESPONSES[key] = {"task": task, "pump": pump}


def unregister_response(key: str) -> None:
    """Remove a completed response from the registry."""
    _ACTIVE_RESPONSES.pop(key, None)


def cancel_user_responses(chat_id: int, user_id: int) -> list[str]:
    """Cancel all active responses for a user in a chat. Returns cancelled keys."""
    prefix = f"telegram:{chat_id}:{user_id}:"
    cancelled = []
    for key in list(_ACTIVE_RESPONSES):
        if key.startswith(prefix):
            entry = _ACTIVE_RESPONSES.pop(key, None)
            if entry is None:
                continue
            # Cancel the task
            task = entry.get("task")
            if task and not task.done():
                task.cancel()
            # Stop the pump
            pump = entry.get("pump")
            if pump:
                try:
                    pump.force_stop()
                except Exception:
                    pass
            cancelled.append(key)
    return cancelled
