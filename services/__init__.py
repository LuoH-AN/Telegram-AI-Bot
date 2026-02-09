"""Services module."""

from .user_service import (
    get_user_settings,
    update_user_setting,
    get_api_key,
    get_base_url,
    get_model,
    get_temperature,
    has_api_key,
)
from .persona_service import (
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
    get_persona_count,
)
from .conversation_service import (
    get_conversation,
    add_message,
    add_user_message,
    add_assistant_message,
    clear_conversation,
    get_message_count,
    pop_last_exchange,
)
from .token_service import (
    get_token_usage,
    add_token_usage,
    get_token_limit,
    set_token_limit,
    reset_token_usage,
    get_total_tokens_all_personas,
    get_remaining_tokens,
    get_usage_percentage,
)
from .export_service import (
    export_to_markdown,
    get_export_filename,
)
from .memory_service import (
    get_memories,
    add_memory,
    delete_memory,
    clear_memories,
    get_memory_count,
    format_memories_for_prompt,
)

__all__ = [
    # User service
    "get_user_settings",
    "update_user_setting",
    "get_api_key",
    "get_base_url",
    "get_model",
    "get_temperature",
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
    "get_persona_count",
    # Conversation service
    "get_conversation",
    "add_message",
    "add_user_message",
    "add_assistant_message",
    "clear_conversation",
    "get_message_count",
    "pop_last_exchange",
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
    "get_export_filename",
    # Memory service
    "get_memories",
    "add_memory",
    "delete_memory",
    "clear_memories",
    "get_memory_count",
    "format_memories_for_prompt",
]
