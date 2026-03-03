"""Per-conversation runtime serialization helpers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

_LOCKS: dict[str, asyncio.Lock] = {}
_LOCKS_GUARD = asyncio.Lock()


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
