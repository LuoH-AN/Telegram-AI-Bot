"""Session cache sync."""

from __future__ import annotations

from database.loaders import parse_conversation_row, parse_session_row


def load(cur, cache) -> None:
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

    cur.execute(
        """
        SELECT session_id, role, content
        FROM user_conversations
        WHERE session_id IS NOT NULL
        ORDER BY id
        """
    )
    conversations: dict[int, list] = {}
    for row in cur.fetchall():
        sid = row["session_id"]
        conversations.setdefault(sid, []).append(parse_conversation_row(row))
    for session_id, messages in conversations.items():
        cache.set_conversation_by_session(session_id, messages)


def sync_titles(cur, dirty: dict) -> None:
    for session_id, title in dirty["dirty_session_titles"].items():
        cur.execute("UPDATE user_sessions SET title = %s WHERE id = %s", (title, session_id))


def sync_deleted(cur, dirty: dict) -> None:
    for session_id in dirty["deleted_sessions"]:
        cur.execute("DELETE FROM user_conversations WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM user_sessions WHERE id = %s", (session_id,))


def sync_cleared(cur, dirty: dict) -> None:
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


def _rekey(cache, dirty: dict, session: dict, old_id: int, new_id: int) -> None:
    if old_id in cache._conversations_cache:
        cache._conversations_cache[new_id] = cache._conversations_cache.pop(old_id)
    if old_id in dirty["conversations"]:
        dirty["conversations"].discard(old_id)
        dirty["conversations"].add(new_id)
    if old_id in dirty["cleared_conversations"]:
        dirty["cleared_conversations"].discard(old_id)
        dirty["cleared_conversations"].add(new_id)
    if old_id in dirty["deleted_sessions"]:
        dirty["deleted_sessions"].discard(old_id)
        dirty["deleted_sessions"].add(new_id)
    if old_id in dirty["dirty_session_titles"]:
        dirty["dirty_session_titles"][new_id] = dirty["dirty_session_titles"].pop(old_id)

    persona = cache.get_persona(session["user_id"], session["persona_name"])
    if persona and persona.get("current_session_id") == old_id:
        persona["current_session_id"] = new_id

    key = (session["user_id"], session["persona_name"])
    for item in cache._sessions_cache.get(key, []):
        if item["id"] == old_id:
            item["id"] = new_id
            break
    cache._session_id_counter = max(cache._session_id_counter, new_id)


def sync_new(cur, cache, dirty: dict) -> None:
    for session in dirty["new_sessions"]:
        cur.execute(
            "INSERT INTO user_sessions (user_id, persona_name, title) VALUES (%s, %s, %s) RETURNING id",
            (session["user_id"], session["persona_name"], session["title"]),
        )
        new_id = cur.fetchone()[0]
        old_id = session["id"]
        session["id"] = new_id
        _rekey(cache, dirty, session, old_id, new_id)
