"""Services module."""

from .user import (
    get_user_settings,
    update_user_setting,
    has_api_key,
)
from .persona import (
    get_personas,
    get_persona,
    get_current_persona,
    get_current_persona_name,
    get_system_prompt,
    switch_persona,
    create_persona,
    delete_persona,
    update_persona_prompt,
    update_current_prompt,
    persona_exists,
)
from cache import cache as _cache
from .token import (
    get_token_usage,
    add_token_usage,
    get_token_limit,
    set_token_limit,
    reset_token_usage,
    get_total_tokens_all_personas,
    get_remaining_tokens,
    get_usage_percentage,
)
from .export import export_to_markdown
from .memory import (
    get_memories,
    add_memory,
    update_memory,
    delete_memory,
    clear_memories,
    format_memories_for_prompt,
)
from .tts import (
    get_voice,
    get_voice_list,
    get_ssml,
    synthesize_voice,
    normalize_tts_endpoint,
)
from .session import (
    get_sessions,
    get_current_session,
    get_current_session_id,
    create_session,
    delete_session as delete_chat_session,
    switch_session,
    rename_session,
    get_session_count,
    get_session_message_count,
    generate_session_title,
)
from .runtime_queue import conversation_slot


# Conversation functions — thin wrappers over cache, no longer in a
# separate service module.  Kept here for backward-compatible imports.

def ensure_session(user_id: int, persona_name: str = None) -> int:
    """Ensure a persona has a current session and return its ID."""
    return _cache.ensure_session_id(user_id, persona_name)


def get_conversation(session_id: int) -> list:
    """Get conversation history for a specific session."""
    return _cache.get_conversation_by_session(session_id)


def add_message(session_id: int, role: str, content: str) -> None:
    """Add a message to a specific session by ID."""
    _cache.add_message_to_session(session_id, role, content)


def add_user_message(session_id: int, content: str) -> None:
    """Add a user message to a specific session."""
    _cache.add_message_to_session(session_id, "user", content)


def add_assistant_message(session_id: int, content: str) -> None:
    """Add an assistant message to a specific session."""
    _cache.add_message_to_session(session_id, "assistant", content)


def clear_conversation(session_id: int) -> None:
    """Clear conversation history for a specific session."""
    _cache.clear_conversation_by_session(session_id)


def get_message_count(session_id: int) -> int:
    """Get number of messages in a session."""
    return len(_cache.get_conversation_by_session(session_id))

__all__ = [
    # User service
    "get_user_settings",
    "update_user_setting",
    "has_api_key",
    # Persona service
    "get_personas",
    "get_persona",
    "get_current_persona",
    "get_current_persona_name",
    "get_system_prompt",
    "switch_persona",
    "create_persona",
    "delete_persona",
    "update_persona_prompt",
    "update_current_prompt",
    "persona_exists",
    # Conversation service
    "ensure_session",
    "get_conversation",
    "add_message",
    "add_user_message",
    "add_assistant_message",
    "clear_conversation",
    "get_message_count",
    # Token service
    "get_token_usage",
    "add_token_usage",
    "get_token_limit",
    "set_token_limit",
    "reset_token_usage",
    "get_total_tokens_all_personas",
    "get_remaining_tokens",
    "get_usage_percentage",
    # Export service
    "export_to_markdown",
    # Memory service
    "get_memories",
    "add_memory",
    "update_memory",
    "delete_memory",
    "clear_memories",
    "format_memories_for_prompt",
    # TTS service
    "get_voice",
    "get_voice_list",
    "get_ssml",
    "synthesize_voice",
    "normalize_tts_endpoint",
    # Session service
    "get_sessions",
    "get_current_session",
    "get_current_session_id",
    "create_session",
    "delete_chat_session",
    "switch_session",
    "rename_session",
    "get_session_count",
    "get_session_message_count",
    "generate_session_title",
    # Runtime queue
    "conversation_slot",
]
