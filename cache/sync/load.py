"""Database-to-cache loading entrypoint."""

from __future__ import annotations

import logging

from database import get_connection, get_dict_cursor

from .load_cron_skills import run_cron_skills_load
from .load_sessions import run_sessions_load
from .load_settings_personas import run_settings_personas_load
from .load_tokens_memories import run_tokens_memories_load

logger = logging.getLogger(__name__)


def load_from_database(cache) -> None:
    try:
        with get_connection() as conn:
            with get_dict_cursor(conn) as cur:
                run_settings_personas_load(cur, cache)
                run_sessions_load(cur, cache)
                run_tokens_memories_load(cur, cache)
                run_cron_skills_load(cur, cache)
    except Exception:
        logger.exception("Failed to load from database")
