"""Cross-process state refresh from database.

This keeps Discord/Telegram/Web consistent when they run in separate processes.
"""

import logging
import os
import threading
import time

from cache import cache, sync_to_database
from database.connection import get_connection, get_dict_cursor
from database.loaders import (
    parse_settings_row,
    parse_persona_row,
    parse_session_row,
    parse_conversation_row,
    parse_token_row,
)

logger = logging.getLogger(__name__)

STATE_REFRESH_INTERVAL = max(0.5, float(os.getenv("STATE_REFRESH_INTERVAL", "2.0")))

_refresh_lock = threading.Lock()
_last_refresh_ts: dict[int, float] = {}


def _has_local_dirty_state(user_id: int) -> bool:
    if user_id in cache._dirty_settings:
        return True
    if any(uid == user_id for uid, _ in cache._dirty_personas):
        return True
    if any(uid == user_id for uid, _ in cache._dirty_tokens):
        return True
    if any(uid == user_id for uid, _ in cache._deleted_personas):
        return True
    if cache._new_sessions or cache._dirty_session_titles or cache._deleted_sessions:
        return True
    if cache._dirty_conversations or cache._cleared_conversations:
        return True
    return False


def _should_refresh(user_id: int, force: bool) -> bool:
    if force:
        return True
    now = time.monotonic()
    with _refresh_lock:
        last = _last_refresh_ts.get(user_id, 0.0)
        if now - last < STATE_REFRESH_INTERVAL:
            return False
        _last_refresh_ts[user_id] = now
    return True


def refresh_user_state_from_db(user_id: int, *, force: bool = False) -> None:
    """Refresh one user's state from DB with throttling."""
    if not _should_refresh(user_id, force):
        return

    if _has_local_dirty_state(user_id):
        try:
            sync_to_database()
        except Exception:
            logger.exception("Failed to flush dirty state before refresh (user=%s)", user_id)
            return

    try:
        conn = get_connection()
        try:
            with get_dict_cursor(conn) as cur:
                cur.execute("SELECT * FROM user_settings WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    cache.set_settings(user_id, parse_settings_row(row))

                cur.execute(
                    """
                    SELECT name, system_prompt, current_session_id
                    FROM user_personas
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                persona_rows = cur.fetchall() or []
                personas = [parse_persona_row(p) for p in persona_rows]
                cache.replace_user_personas(user_id, personas)

                cur.execute(
                    """
                    SELECT id, persona_name, title, created_at
                    FROM user_sessions
                    WHERE user_id = %s
                    ORDER BY id
                    """,
                    (user_id,),
                )
                session_rows = cur.fetchall() or []
                sessions_by_persona: dict[str, list[dict]] = {}
                session_ids: set[int] = set()
                for row in session_rows:
                    session = parse_session_row(row, user_id=user_id)
                    sessions_by_persona.setdefault(row["persona_name"], []).append(session)
                    session_ids.add(row["id"])
                cache.replace_user_sessions(user_id, sessions_by_persona)

                conversations_by_session: dict[int, list[dict]] = {session_id: [] for session_id in session_ids}
                if session_ids:
                    cur.execute(
                        """
                        SELECT c.session_id, c.role, c.content
                        FROM user_conversations c
                        JOIN user_sessions s ON s.id = c.session_id
                        WHERE s.user_id = %s AND c.session_id IS NOT NULL
                        ORDER BY c.id
                        """,
                        (user_id,),
                    )
                    for row in cur.fetchall() or []:
                        conversations_by_session.setdefault(row["session_id"], []).append(
                            parse_conversation_row(row)
                        )
                for session_id, messages in conversations_by_session.items():
                    cache.set_conversation_by_session(session_id, messages)

                cur.execute(
                    """
                    SELECT persona_name, prompt_tokens, completion_tokens, total_tokens, token_limit
                    FROM user_persona_tokens
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                token_rows = cur.fetchall() or []
                usage_by_persona: dict[str, dict] = {}
                for token_row in token_rows:
                    usage_by_persona[token_row["persona_name"]] = parse_token_row(token_row)
                cache.replace_user_token_usage(user_id, usage_by_persona)
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to refresh user state from DB (user=%s)", user_id)
