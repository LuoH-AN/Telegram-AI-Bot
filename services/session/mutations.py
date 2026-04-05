"""Session write operations."""

from cache import cache


def _resolve_persona_name(user_id: int, persona_name: str | None) -> str:
    return persona_name or cache.get_current_persona_name(user_id)


def create_session(user_id: int, persona_name: str = None, title: str = None) -> dict:
    persona = _resolve_persona_name(user_id, persona_name)
    session = cache.create_session(user_id, persona, title)
    cache.set_current_session_id(user_id, persona, session["id"])
    return session


def delete_session(user_id: int, session_index: int, persona_name: str = None) -> bool:
    persona = _resolve_persona_name(user_id, persona_name)
    sessions = cache.get_sessions(user_id, persona)
    if session_index < 1 or session_index > len(sessions):
        return False

    session_id = sessions[session_index - 1]["id"]
    current_id = cache.get_current_session_id(user_id, persona)
    cache.delete_session(session_id, user_id, persona)

    if current_id != session_id:
        return True

    remaining = cache.get_sessions(user_id, persona)
    if remaining:
        cache.set_current_session_id(user_id, persona, remaining[-1]["id"])
        return True

    new_session = cache.create_session(user_id, persona)
    cache.set_current_session_id(user_id, persona, new_session["id"])
    return True


def switch_session(user_id: int, session_index: int, persona_name: str = None) -> bool:
    persona = _resolve_persona_name(user_id, persona_name)
    sessions = cache.get_sessions(user_id, persona)
    if session_index < 1 or session_index > len(sessions):
        return False
    cache.set_current_session_id(user_id, persona, sessions[session_index - 1]["id"])
    return True


def rename_session(user_id: int, title: str, persona_name: str = None) -> bool:
    persona = _resolve_persona_name(user_id, persona_name)
    session_id = cache.get_current_session_id(user_id, persona)
    if session_id is None:
        return False
    cache.update_session_title(session_id, title)
    return True

