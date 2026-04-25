"""Centralized user state refresh.

Call ``ensure_user_state(user_id)`` once at the handler entry point
instead of having every individual service getter call
``refresh_user_state_from_db``.
"""

from __future__ import annotations

from .state import refresh_user_state_from_db


def ensure_user_state(user_id: int, *, force: bool = False) -> None:
    """Ensure the in-memory cache for *user_id* is up-to-date.

    Should be called once at the handler entry point.  The underlying
    implementation debounces automatically (time-based), so repeated
    calls within a short window are cheap no-ops unless *force* is set.
    """
    refresh_user_state_from_db(user_id, force=force)
