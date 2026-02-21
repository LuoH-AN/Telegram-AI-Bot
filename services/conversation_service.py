"""Conversation management service."""

from cache import cache


def ensure_session(user_id: int, persona_name: str = None) -> int:
    """Ensure a persona has a current session and return its ID."""
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


def pop_last_exchange(session_id: int) -> bool:
    """Remove the last user+assistant message pair from conversation.

    Returns True if messages were removed, False if conversation was empty.
    """
    conversation = cache.get_conversation_by_session(session_id)
    if not conversation:
        return False
    # Remove trailing assistant message(s), then the last user message
    while conversation and conversation[-1]["role"] == "assistant":
        conversation.pop()
    if conversation and conversation[-1]["role"] == "user":
        conversation.pop()
    return True
