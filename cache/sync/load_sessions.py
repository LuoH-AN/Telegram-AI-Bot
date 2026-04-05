"""Load sessions and conversations into cache."""

from __future__ import annotations

from database.loaders import parse_conversation_row, parse_session_row


def load_sessions(cur, cache) -> None:
    max_session_id = 0
    cur.execute("SELECT id, user_id, persona_name, title, created_at FROM user_sessions ORDER BY id")
    sessions_by_key: dict[tuple[int, str], list[dict]] = {}
    for row in cur.fetchall():
        session = parse_session_row(row)
        key = (session["user_id"], session["persona_name"])
        sessions_by_key.setdefault(key, []).append(session)
        max_session_id = max(max_session_id, row["id"])
    for key, sessions in sessions_by_key.items():
        cache.set_sessions(key[0], key[1], sessions)
    cache._session_id_counter = max_session_id


def load_conversations(cur, cache) -> None:
    cur.execute(
        """
        SELECT session_id, role, content
        FROM user_conversations
        WHERE session_id IS NOT NULL
        ORDER BY id
        """
    )
    conversations_by_session: dict[int, list] = {}
    for row in cur.fetchall():
        sid = row["session_id"]
        conversations_by_session.setdefault(sid, []).append(parse_conversation_row(row))
    for session_id, messages in conversations_by_session.items():
        cache.set_conversation_by_session(session_id, messages)


def run_sessions_load(cur, cache) -> None:
    load_sessions(cur, cache)
    load_conversations(cur, cache)
