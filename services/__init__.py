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
from .skills import (
    list_skills,
    get_skill,
    install_skill,
    install_skill_from_github,
    enable_skill,
    remove_skill,
    call_skill,
    persist_skill_state,
    persist_skill_snapshot,
    list_skill_snapshots,
    restore_skill,
    restore_skill_snapshot,
    auto_restore_skills,
)
from .skill_terminal import run_skill_terminal
from .terminal_exec import execute_terminal_command
from .hot_update import run_hot_update, schedule_process_restart
from .hot_update import run_safe_restart
def ensure_session(user_id: int, persona_name: str = None) -> int:
    return _cache.ensure_session_id(user_id, persona_name)

def get_conversation(session_id: int) -> list:
    return _cache.get_conversation_by_session(session_id)

def add_message(session_id: int, role: str, content: str) -> None:
    _cache.add_message_to_session(session_id, role, content)

def add_user_message(session_id: int, content: str) -> None:
    _cache.add_message_to_session(session_id, "user", content)

def add_assistant_message(session_id: int, content: str) -> None:
    _cache.add_message_to_session(session_id, "assistant", content)

def clear_conversation(session_id: int) -> None:
    _cache.clear_conversation_by_session(session_id)

def get_message_count(session_id: int) -> int:
    return len(_cache.get_conversation_by_session(session_id))
