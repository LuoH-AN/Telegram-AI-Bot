"""Shared platform-facing text and logging helpers."""

from .chat import (
    build_chat_commands_message,
    build_chat_no_sessions_message,
    build_chat_unknown_subcommand_message,
)
from .config import SHARED_TOOL_STATUS_MAP, SET_COMMAND_KEYS, _build_set_key_lines
from .help import (
    build_advanced_help_section,
    build_help_message,
    build_memory_help_section,
    build_persona_help_section,
    build_settings_help_section,
    build_start_message_missing_api,
    build_start_message_returning,
    format_log_context,
)
from .memory import (
    build_api_key_required_message,
    build_forget_invalid_target_message,
    build_forget_usage_message,
    build_invalid_memory_number_message,
    build_latex_guidance,
    build_memory_empty_message,
    build_memory_list_footer_message,
    build_remember_usage_message,
    build_retry_message,
    build_token_limit_reached_message,
    build_usage_reset_message,
)
from .persona import (
    build_persona_commands_message,
    build_persona_created_message,
    build_persona_new_usage_message,
    build_persona_not_found_message,
    build_persona_prompt_overview_message,
)
from .provider import (
    build_provider_list_usage_message,
    build_provider_no_saved_message,
    build_provider_not_found_available_message,
    build_provider_save_hint_message,
    build_provider_usage_message,
)
from .settings import (
    build_api_key_verify_failed_message,
    build_api_key_verify_no_models_message,
    build_global_prompt_help_message,
    build_prompt_per_persona_message,
    build_reasoning_effort_help_message,
    build_set_usage_message,
    build_settings_summary_message,
    build_show_thinking_help_message,
    build_stream_mode_help_message,
    build_unknown_set_key_message,
)
from .web import (
    build_analyze_uploaded_files_message,
    build_web_dashboard_message,
    build_web_dm_failed_message,
    build_web_dm_sent_message,
)
