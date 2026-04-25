"""Session read accessors."""

from cache import cache


def get_sessions(user_id: int, persona_name: str = None) -> list[dict]:
    return cache.get_sessions(user_id, persona_name)


def get_current_session_id(user_id: int, persona_name: str = None) -> int | None:
    if persona_name is None:
        persona_name = cache.get_current_persona_name(user_id)
    return cache.get_current_session_id(user_id, persona_name)


def get_current_session(user_id: int, persona_name: str = None) -> dict | None:
    session_id = get_current_session_id(user_id, persona_name)
    if session_id is None:
        return None
    return cache.get_session_by_id(session_id)

