"""Sync session metadata and conversation rows."""

from __future__ import annotations


def sync_session_titles(cur, dirty: dict) -> None:
    for session_id, title in dirty["dirty_session_titles"].items():
        cur.execute("UPDATE user_sessions SET title = %s WHERE id = %s", (title, session_id))


def sync_deleted_sessions(cur, dirty: dict) -> None:
    for session_id in dirty["deleted_sessions"]:
        cur.execute("DELETE FROM user_conversations WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM user_sessions WHERE id = %s", (session_id,))


def sync_cleared_conversations(cur, dirty: dict) -> None:
    for session_id in dirty["cleared_conversations"]:
        cur.execute("DELETE FROM user_conversations WHERE session_id = %s", (session_id,))


def sync_conversations(cur, cache, dirty: dict) -> None:
    for session_id in dirty["conversations"]:
        session = cache.get_session_by_id(session_id)
        if not session:
            continue
        cur.execute("SELECT COUNT(*) FROM user_conversations WHERE session_id = %s", (session_id,))
        db_count = cur.fetchone()[0]
        cached = cache.get_conversation_by_session(session_id)
        for msg in cached[db_count:]:
            cur.execute(
                "INSERT INTO user_conversations (user_id, persona_name, session_id, role, content) VALUES (%s, %s, %s, %s, %s)",
                (session["user_id"], session["persona_name"], session_id, msg["role"], msg["content"]),
            )
