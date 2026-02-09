"""Conversation management service."""

from cache import cache


def get_conversation(user_id: int, persona_name: str = None) -> list:
    """Get conversation history for a user's current or specified persona."""
    return cache.get_conversation(user_id, persona_name)


def add_message(user_id: int, role: str, content: str, persona_name: str = None) -> None:
    """Add a message to conversation history."""
    cache.add_message(user_id, role, content, persona_name)


def add_user_message(user_id: int, content: str, persona_name: str = None) -> None:
    """Add a user message to conversation history."""
    cache.add_message(user_id, "user", content, persona_name)


def add_assistant_message(user_id: int, content: str, persona_name: str = None) -> None:
    """Add an assistant message to conversation history."""
    cache.add_message(user_id, "assistant", content, persona_name)


def clear_conversation(user_id: int, persona_name: str = None) -> None:
    """Clear conversation history for the current or specified persona."""
    cache.clear_conversation(user_id, persona_name)


def get_message_count(user_id: int, persona_name: str = None) -> int:
    """Get number of messages in conversation."""
    return len(cache.get_conversation(user_id, persona_name))


def pop_last_exchange(user_id: int, persona_name: str = None) -> bool:
    """Remove the last user+assistant message pair from conversation.

    Returns True if messages were removed, False if conversation was empty.
    """
    conversation = cache.get_conversation(user_id, persona_name)
    if not conversation:
        return False
    # Remove trailing assistant message(s), then the last user message
    while conversation and conversation[-1]["role"] == "assistant":
        conversation.pop()
    if conversation and conversation[-1]["role"] == "user":
        conversation.pop()
    return True
