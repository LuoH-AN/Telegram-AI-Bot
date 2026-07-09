"""Reload a session's full conversation from the DB (eviction reload-on-demand)."""

from __future__ import annotations

from infrastructure.database.db import get_connection, get_dict_cursor
from infrastructure.database.loaders import parse_conversation_row


def load_session_messages(session_id: int) -> list[dict]:
    """Return all persisted messages for a session, in order. Empty if none."""
    conn = get_connection()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute(
                "SELECT role, content, reasoning_content FROM user_conversations "
                "WHERE session_id = %s ORDER BY id",
                (session_id,),
            )
            return [parse_conversation_row(row) for row in cur.fetchall()]
    finally:
        conn.close()
