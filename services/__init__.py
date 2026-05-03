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
from .conversation import (
    ensure_session,
    get_conversation,
    add_message,
    add_user_message,
    add_assistant_message,
    clear_conversation,
    get_message_count,
)
from .queue import conversation_slot
from .update import run_hot_update, schedule_process_restart, run_safe_restart

__all__ = [
    "get_user_settings", "update_user_setting", "has_api_key",
    "get_personas", "get_persona", "get_current_persona", "get_current_persona_name",
    "get_system_prompt", "switch_persona", "create_persona", "delete_persona",
    "update_persona_prompt", "update_current_prompt", "persona_exists",
    "get_token_usage", "add_token_usage", "get_token_limit", "set_token_limit",
    "reset_token_usage", "get_total_tokens_all_personas",
    "get_remaining_tokens", "get_usage_percentage",
    "export_to_markdown",
    "get_memories", "add_memory", "update_memory", "delete_memory",
    "clear_memories", "format_memories_for_prompt",
    "get_sessions", "get_current_session", "get_current_session_id",
    "create_session", "delete_chat_session", "switch_session", "rename_session",
    "get_session_count", "get_session_message_count", "generate_session_title",
    "ensure_session", "get_conversation", "add_message",
    "add_user_message", "add_assistant_message",
    "clear_conversation", "get_message_count",
    "conversation_slot",
    "run_hot_update", "schedule_process_restart", "run_safe_restart",
]
