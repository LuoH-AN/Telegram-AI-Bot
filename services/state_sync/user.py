"""Public user refresh entrypoint."""

import logging

from cache import sync_to_database

from .db import refresh_cache_from_db
from .dirty import has_local_dirty_state
from .policy import should_refresh

logger = logging.getLogger(__name__)


def refresh_user_state_from_db(user_id: int, *, force: bool = False) -> None:
    if not should_refresh(user_id, force):
        return

    if has_local_dirty_state(user_id):
        try:
            sync_to_database()
        except Exception:
            logger.exception("Failed to flush dirty state before refresh (user=%s)", user_id)
            return

    try:
        refresh_cache_from_db(user_id)
    except Exception:
        logger.exception("Failed to refresh user state from DB (user=%s)", user_id)
