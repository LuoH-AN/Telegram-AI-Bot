"""Session statistics helpers."""

from cache import cache


def get_session_count(user_id: int, persona_name: str = None) -> int:
    return len(cache.get_sessions(user_id, persona_name))


def get_session_message_count(session_id: int) -> int:
    return len(cache.get_conversation_by_session(session_id))

