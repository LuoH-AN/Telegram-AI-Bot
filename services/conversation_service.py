"""Conversation management service."""

from cache import cache
from .state_sync_service import refresh_user_state_from_db


def ensure_session(user_id: int, persona_name: str = None) -> int:
    """Ensure a persona has a current session and return its ID."""
    refresh_user_state_from_db(user_id)
    return cache.ensure_session_id(user_id, persona_name)


def get_conversation(session_id: int) -> list:
    """Get conversation history for a specific session."""
    return cache.get_conversation_by_session(session_id)


def add_message(session_id: int, role: str, content: str) -> None:
    """Add a message to a specific session by ID."""
    cache.add_message_to_session(session_id, role, content)


def add_user_message(session_id: int, content: str) -> None:
    """Add a user message to a specific session."""
    cache.add_message_to_session(session_id, "user", content)


def add_assistant_message(session_id: int, content: str) -> None:
    """Add an assistant message to a specific session."""
    cache.add_message_to_session(session_id, "assistant", content)


def clear_conversation(session_id: int) -> None:
    """Clear conversation history for a specific session."""
    cache.clear_conversation_by_session(session_id)


def get_message_count(session_id: int) -> int:
    """Get number of messages in a session."""
    return len(cache.get_conversation_by_session(session_id))
