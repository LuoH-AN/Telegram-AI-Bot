"""Database-to-cache loading entrypoint."""

from __future__ import annotations

import logging

from database import get_connection, get_dict_cursor

from . import cron, memory, persona, session, settings, skill, token

logger = logging.getLogger(__name__)


def load_from_database(cache) -> None:
    try:
        with get_connection() as conn:
            with get_dict_cursor(conn) as cur:
                settings.load(cur, cache)
                persona.load(cur, cache)
                session.load(cur, cache)
                token.load(cur, cache)
                memory.load(cur, cache)
                cron.load(cur, cache)
                skill.load(cur, cache)
    except Exception:
        logger.exception("Failed to load from database")
