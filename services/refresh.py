"""Centralized user state refresh.

Call ``await ensure_user_state(user_id)`` once at the handler entry point
instead of having every individual service getter call
``refresh_user_state_from_db``.
"""

from __future__ import annotations

import asyncio

from plugins.project_config.sync.user import refresh_user_state_from_db


async def ensure_user_state(user_id: int, *, force: bool = False) -> None:
    """Ensure the in-memory cache for *user_id* is up-to-date.

    The underlying refresh is debounced (time-based) inside
    ``refresh_user_state_from_db``; most calls within a short window are
    cheap no-ops. Real DB work is dispatched to a thread to avoid
    blocking the event loop.
    """
    await asyncio.to_thread(refresh_user_state_from_db, user_id, force=force)
