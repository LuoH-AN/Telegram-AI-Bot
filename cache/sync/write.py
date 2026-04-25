"""Cache-to-database syncing entrypoint."""

from __future__ import annotations

import logging

from database import get_connection

from . import cron, memory, persona, session, settings, skill, token
from .summary import log_sync_summary

logger = logging.getLogger(__name__)


def sync_to_database(cache) -> None:
    dirty = cache.get_and_clear_dirty()
    if not any(dirty.values()):
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                settings.sync(cur, cache, dirty)
                persona.sync_deleted(cur, dirty)
                persona.sync(cur, cache, dirty)
                session.sync_new(cur, cache, dirty)
                session.sync_titles(cur, dirty)
                session.sync_deleted(cur, dirty)
                session.sync_cleared(cur, dirty)
                session.sync_conversations(cur, cache, dirty)
                token.sync(cur, cache, dirty)
                memory.sync(cur, dirty)
                cron.sync_deleted(cur, dirty)
                cron.sync_new(cur, dirty)
                cron.sync_updated(cur, dirty)
                skill.sync_deleted(cur, dirty)
                skill.sync_new(cur, dirty)
                skill.sync_updated(cur, dirty)
                skill.sync_states(cur, dirty)
            conn.commit()
        log_sync_summary(logger, dirty)
    except Exception:
        cache.restore_dirty(dirty)
        logger.exception("Failed to sync to database")
