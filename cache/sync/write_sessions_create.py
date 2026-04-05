"""Sync new sessions and remap temporary ids."""

from __future__ import annotations


def _rekey_new_session_id(cache, dirty: dict, session: dict, old_id: int, new_id: int) -> None:
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


def sync_new_sessions(cur, cache, dirty: dict) -> None:
    for session in dirty["new_sessions"]:
        cur.execute(
            "INSERT INTO user_sessions (user_id, persona_name, title) VALUES (%s, %s, %s) RETURNING id",
            (session["user_id"], session["persona_name"], session["title"]),
        )
        new_id = cur.fetchone()[0]
        old_id = session["id"]
        session["id"] = new_id
        _rekey_new_session_id(cache, dirty, session, old_id, new_id)
