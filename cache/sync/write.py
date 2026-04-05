"""Cache-to-database syncing entrypoint."""

from __future__ import annotations

import logging

from database import get_connection

from .write_cron import sync_deleted_cron_tasks, sync_new_cron_tasks, sync_updated_cron_tasks
from .write_sessions_conversations import (
    sync_cleared_conversations,
    sync_conversations,
    sync_deleted_sessions,
    sync_session_titles,
)
from .write_sessions_create import sync_new_sessions
from .write_settings_personas import sync_deleted_personas, sync_personas, sync_settings
from .write_skill_states import sync_skill_states
from .write_skills_delete import sync_deleted_skills
from .write_skills_upsert import sync_new_skills, sync_updated_skills
from .write_summary import log_sync_summary
from .write_tokens_memories import sync_memories, sync_tokens

logger = logging.getLogger(__name__)


def sync_to_database(cache) -> None:
    dirty = cache.get_and_clear_dirty()
    if not any(dirty.values()):
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                sync_settings(cur, cache, dirty)
                sync_deleted_personas(cur, dirty)
                sync_personas(cur, cache, dirty)
                sync_new_sessions(cur, cache, dirty)
                sync_session_titles(cur, dirty)
                sync_deleted_sessions(cur, dirty)
                sync_cleared_conversations(cur, dirty)
                sync_conversations(cur, cache, dirty)
                sync_tokens(cur, cache, dirty)
                sync_memories(cur, dirty)
                sync_deleted_cron_tasks(cur, dirty)
                sync_new_cron_tasks(cur, dirty)
                sync_updated_cron_tasks(cur, dirty)
                sync_deleted_skills(cur, dirty)
                sync_new_skills(cur, dirty)
                sync_updated_skills(cur, dirty)
                sync_skill_states(cur, dirty)
            conn.commit()
        log_sync_summary(logger, dirty)
    except Exception:
        cache.restore_dirty(dirty)
        logger.exception("Failed to sync to database")
