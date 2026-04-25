"""Dirty-state checks before DB refresh."""

from cache import cache


def has_local_dirty_state(user_id: int) -> bool:
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
    if any(uid == user_id for uid, _ in cache._deleted_skills):
        return True
    if cache._new_skills or cache._updated_skills or cache._updated_skill_states:
        return True
    return False

