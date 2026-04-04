"""Shared platform-facing text and logging helpers.

This module keeps Telegram and Discord behavior aligned by centralizing
user-facing text and log context formatting.
"""

from __future__ import annotations

SHARED_TOOL_STATUS_MAP = {
    "web_search": "Searching...",
    "url_fetch": "Fetching page...",
    "save_memory": "Saving to memory...",
    "tts_speak": "Generating voice...",
    "tts_list_voices": "Loading voices...",
    "shell_exec": "Running command...",
    "cron_create": "Creating scheduled task...",
    "cron_list": "Listing scheduled tasks...",
    "cron_delete": "Deleting scheduled task...",
    "cron_run": "Running scheduled task...",
    "page_screenshot": "Taking screenshot...",
    "page_content": "Extracting page content...",
    "browser_start_session": "Starting browser session...",
    "browser_list_sessions": "Listing browser sessions...",
    "browser_close_session": "Closing browser session...",
    "browser_goto": "Navigating browser...",
    "browser_click": "Clicking page element...",
    "browser_type": "Typing into page...",
    "browser_press": "Sending key press...",
    "browser_wait_for": "Waiting for page condition...",
    "browser_get_state": "Reading page state...",
}

SET_COMMAND_KEYS = (
    "base_url",
    "api_key",
    "model",
    "temperature",
    "reasoning_effort",
    "show_thinking",
    "stream_mode",
    "token_limit",
    "global_prompt",
    "title_model",
    "cron_model",
    "voice",
    "style",
    "endpoint",
    "provider",
)


def _build_set_key_lines() -> str:
    return (
        "- base_url - API endpoint\n"
        "- api_key - API key\n"
        "- model - model (no value to browse list)\n"
        "- temperature - temperature parameter\n"
        "- reasoning_effort - reasoning effort (none/minimal/low/medium/high/xhigh)\n"
        "- show_thinking - show condensed reasoning block when available (on/off)\n"
        "- stream_mode - streaming mode (default/time/chars/off)\n"
        "- token_limit - token limit for current persona\n"
        "- global_prompt - global prompt (<text|clear>)\n"
        "- title_model - title generation model [provider:]model\n"
        "- cron_model - cron task model [provider:]model\n"
        "- voice - TTS voice\n"
        "- style - TTS style\n"
        "- endpoint - TTS endpoint\n"
        "- provider - provider management (list/save/load/delete)"
    )


def format_log_context(*, platform: str, user_id: int, scope: str, chat_id: int) -> str:
    return f"[platform={platform} user={user_id} scope={scope} chat={chat_id}]"


def build_start_message_missing_api(prefix: str) -> str:
    return (
        "Welcome to AI Bot!\n\n"
        "First, set your API key:\n"
        f"{prefix}set api_key YOUR_API_KEY\n\n"
        "Optional configuration:\n"
        f"{prefix}set base_url <url> - API endpoint\n"
        f"{prefix}set model <name> - choose model\n\n"
        f"Type {prefix}help for all commands."
    )


def build_start_message_returning(persona: str, prefix: str) -> str:
    return (
        f"Welcome back! Current persona: {persona}\n\n"
        f"Send a message to chat, or use {prefix}help for commands."
    )


def build_help_message(prefix: str) -> str:
    return (
        "AI Bot Help\n\n"
        "Send text, images, or files to chat with AI.\n"
        "AI can use installed tools and skills during chat when the current model supports them.\n\n"
        "In groups/servers: mention the bot or reply to a bot message\n"
        "In private chats/DMs: direct chat works\n\n"
        "Commands:\n"
        f"{prefix}start - show welcome message\n"
        f"{prefix}help - show this help\n"
        f"{prefix}persona - manage personas\n"
        f"{prefix}chat - manage sessions\n"
        f"{prefix}settings - view settings\n"
        f"{prefix}set <key> <value> - modify settings\n"
        f"{prefix}stop - stop active response\n"
        f"{prefix}skill - manage skills\n"
        f"{prefix}remember <text> - add memory\n"
        f"{prefix}memories - view memories\n"
        f"{prefix}forget <num|all> - delete memory\n"
        f"{prefix}usage - view usage\n"
        f"{prefix}export - export conversation\n"
        f"{prefix}clear - clear conversation\n"
        f"{prefix}web - open dashboard"
    )


def build_persona_help_section(prefix: str) -> str:
    return (
        "Persona Commands\n\n"
        f"{prefix}persona - list all personas\n"
        f"{prefix}persona <name> - switch to persona\n"
        f"{prefix}persona new <name> [prompt] - create persona\n"
        f"{prefix}persona delete <name> - delete persona\n"
        f"{prefix}persona prompt <text> - set current persona prompt\n\n"
        "Each persona has independent sessions and token usage."
    )


def build_settings_help_section(prefix: str) -> str:
    return (
        "Settings Commands\n\n"
        f"{prefix}settings - show current settings\n"
        f"{prefix}set <key> <value> - update a setting\n"
        f"{prefix}set model - browse or list models\n"
        f"{prefix}set stream_mode - show stream mode help\n"
        f"{prefix}set show_thinking - show thinking help\n"
        f"{prefix}set reasoning_effort - show reasoning help\n"
        f"{prefix}set global_prompt - show global prompt help\n\n"
        "Available keys:\n"
        f"{_build_set_key_lines()}\n\n"
        "Provider presets:\n"
        f"{prefix}set provider list\n"
        f"{prefix}set provider save <name>\n"
        f"{prefix}set provider load <name>\n"
        f"{prefix}set provider delete <name>"
    )


def build_memory_help_section(prefix: str) -> str:
    return (
        "Memory Commands\n\n"
        f"{prefix}remember <text> - add a memory\n"
        f"{prefix}memories - list all memories\n"
        f"{prefix}forget <num|all> - delete memories\n\n"
        "Memories are shared across all personas.\n"
        "AI can also save useful memories automatically."
    )


def build_advanced_help_section(prefix: str) -> str:
    return (
        "Advanced\n\n"
        f"{prefix}chat - manage chat sessions\n"
        f"{prefix}export - export current session history\n"
        f"{prefix}usage - show token usage\n"
        f"{prefix}clear - clear current session conversation\n"
        f"{prefix}stop - stop active response\n"
        f"{prefix}web - open the web dashboard\n\n"
        "Session Commands:\n"
        f"{prefix}chat - list sessions\n"
        f"{prefix}chat new [title] - create session\n"
        f"{prefix}chat <num> - switch session\n"
        f"{prefix}chat rename <title> - rename session\n"
        f"{prefix}chat delete <num> - delete session\n\n"
        "Features:\n"
        "- Token limit is tracked per persona\n"
        "- Send images or files for AI analysis\n"
        "- stream_mode off sends one full reply at the end\n"
        "- title_model and cron_model can use [provider:]model"
    )


def build_api_key_required_message(prefix: str) -> str:
    return f"Please set your API key first:\n{prefix}set api_key YOUR_API_KEY"


def build_token_limit_reached_message(prefix: str, persona_name: str) -> str:
    return (
        f"Persona '{persona_name}' has reached token limit.\n"
        f"Use {prefix}usage to view usage, or "
        f"{prefix}set token_limit <number> to adjust limit."
    )


def build_latex_guidance() -> str:
    return (
        "\n\nImportant: Avoid using LaTeX delimiters ($...$ / $$...$$). "
        "Use plain text and Unicode math symbols (like × ÷ √ π ≤ ≥)."
    )


def build_memory_empty_message(prefix: str) -> str:
    return (
        "No memories yet.\n\n"
        f"Use {prefix}remember <content> to add a memory.\n"
        "AI can also automatically add memories during conversation."
    )


def build_forget_usage_message(prefix: str) -> str:
    return (
        "Usage:\n"
        f"{prefix}forget <number> - delete specific memory\n"
        f"{prefix}forget all - clear all memories\n\n"
        f"Use {prefix}memories to view numbered list."
    )


def build_usage_reset_message(persona_name: str) -> str:
    return f"Usage for persona '{persona_name}' has been reset."


def build_persona_new_usage_message(prefix: str) -> str:
    return (
        f"Usage: {prefix}persona new <name> [system prompt]\n\n"
        "Example:\n"
        f"{prefix}persona new coder You are a coding assistant."
    )


def build_persona_created_message(name: str, prefix: str) -> str:
    return (
        f"Created and switched to persona: {name}\n\n"
        f"Use {prefix}persona prompt <text> to set system prompt."
    )


def build_persona_prompt_overview_message(name: str, prompt: str, prefix: str) -> str:
    return (
        f"Current persona: {name}\n\n"
        f"Prompt: {prompt}\n\n"
        f"Usage: {prefix}persona prompt <new prompt>"
    )


def build_persona_not_found_message(name: str, prefix: str) -> str:
    return f"Persona '{name}' does not exist. Use {prefix}persona new {name} to create."


def build_persona_commands_message(prefix: str) -> str:
    return (
        "Commands:\n"
        f"{prefix}persona <name> - switch\n"
        f"{prefix}persona new <name> - create\n"
        f"{prefix}persona delete <name> - delete\n"
        f"{prefix}persona prompt <text> - set prompt"
    )


def build_chat_no_sessions_message(persona_name: str, prefix: str) -> str:
    return (
        f"Persona '{persona_name}' has no sessions yet.\n"
        f"Send a message to auto-create, or use {prefix}chat new"
    )


def build_chat_unknown_subcommand_message(prefix: str) -> str:
    return (
        "Unknown subcommand. Usage:\n\n"
        f"{prefix}chat - list sessions\n"
        f"{prefix}chat new [title] - create session\n"
        f"{prefix}chat <number> - switch session\n"
        f"{prefix}chat rename <title> - rename\n"
        f"{prefix}chat delete <number> - delete"
    )


def build_chat_commands_message(prefix: str) -> str:
    return (
        f"{prefix}chat <number> - switch\n"
        f"{prefix}chat new [title] - create session\n"
        f"{prefix}chat rename <title> - rename\n"
        f"{prefix}chat delete <number> - delete"
    )


def build_web_dashboard_message(url: str) -> str:
    return (
        "Open Gemen dashboard:\n"
        f"{url}\n\n"
        "This link expires in 10 minutes."
    )


def build_web_dm_sent_message() -> str:
    return "Dashboard link sent to DM."


def build_web_dm_failed_message() -> str:
    return "Cannot send DM. Please enable DMs and try again."


def build_retry_message() -> str:
    return "An error occurred. Please try again."


def build_remember_usage_message(prefix: str) -> str:
    return (
        f"Usage: {prefix}remember <content>\n\n"
        f"Example: {prefix}remember I prefer concise answers"
    )


def build_memory_list_footer_message(prefix: str) -> str:
    return (
        "\n[user] = added by you\n"
        "[AI] = added by AI\n"
        f"\nUse {prefix}forget <number> to delete\n"
        f"Use {prefix}forget all to clear all"
    )


def build_forget_invalid_target_message(prefix: str) -> str:
    return (
        "Please specify a number or 'all'.\n"
        f"Example: {prefix}forget 1 or {prefix}forget all"
    )


def build_invalid_memory_number_message(index: int, prefix: str) -> str:
    return (
        f"Invalid memory number: {index}\n"
        f"Use {prefix}memories to view list."
    )


def build_set_usage_message(prefix: str) -> str:
    return (
        f"Usage: {prefix}set <key> <value>\n\n"
        "Available keys:\n"
        f"{_build_set_key_lines()}\n\n"
        f"Use {prefix}set provider for provider preset commands.\n"
        f"Use {prefix}persona prompt <text> to set the current persona prompt."
    )


def build_stream_mode_help_message(prefix: str, current: str) -> str:
    return (
        f"Current stream_mode: {current}\n"
        f"Usage: {prefix}set stream_mode <mode>\n\n"
        "Available modes:\n"
        "- default: time + chars combined\n"
        "- time: update by time interval\n"
        "- chars: update by character interval\n"
        "- off: non-streaming, wait for full response (reduces rate limits)\n\n"
        f"Use {prefix}set stream_mode clear to return to default mode."
    )


def build_show_thinking_help_message(prefix: str, current: str) -> str:
    return (
        f"Current show_thinking: {current}\n"
        f"Usage: {prefix}set show_thinking <on|off>\n\n"
        "When enabled, supported models may show a condensed reasoning block in the final answer."
    )


def build_reasoning_effort_help_message(prefix: str, current: str) -> str:
    return (
        f"Current reasoning_effort: {current}\n"
        f"Usage: {prefix}set reasoning_effort <value>\n\n"
        "Available values:\n"
        "- none\n"
        "- minimal\n"
        "- low\n"
        "- medium\n"
        "- high\n"
        "- xhigh\n\n"
        f"Use {prefix}set reasoning_effort clear to follow provider/model default."
    )


def build_global_prompt_help_message(prefix: str, current: str) -> str:
    return (
        f"Current global_prompt: {current}\n\n"
        f"Usage: {prefix}set global_prompt <prompt>\n"
        f"Use {prefix}set global_prompt clear to remove."
    )


def build_prompt_per_persona_message(prefix: str) -> str:
    return (
        "Prompts are now managed per persona.\n"
        f"Use {prefix}persona prompt <text> to set prompt for current persona."
    )


def build_settings_summary_message(
    prefix: str,
    *,
    base_url: str,
    masked_api_key: str,
    model: str,
    temperature: float,
    reasoning_effort: str,
    show_thinking: str,
    stream_mode: str,
    title_model: str,
    cron_model: str,
    persona_name: str,
    token_limit_display: str,
    global_prompt: str,
    prompt: str,
    tts_voice: str,
    tts_style: str,
    tts_endpoint: str,
    providers_info: str,
) -> str:
    return (
        "Current Settings:\n\n"
        f"base_url: {base_url}\n"
        f"api_key: {masked_api_key}\n"
        f"model: {model}\n"
        f"temperature: {temperature}\n"
        f"reasoning_effort: {reasoning_effort}\n"
        f"show_thinking: {show_thinking}\n"
        f"stream_mode: {stream_mode}\n"
        f"title_model: {title_model}\n"
        f"cron_model: {cron_model}\n"
        f"persona: {persona_name}\n"
        f"token_limit({persona_name}): {token_limit_display}\n"
        f"global_prompt: {global_prompt}\n"
        f"prompt: {prompt}\n"
        f"tts_voice: {tts_voice}\n"
        f"tts_style: {tts_style}\n"
        f"tts_endpoint: {tts_endpoint}\n\n"
        f"providers: {providers_info}\n\n"
        f"Use {prefix}persona to manage personas and prompts.\n"
        f"Use {prefix}chat to manage chat sessions.\n"
        f"Use {prefix}set provider to manage API providers."
    )


def build_endpoint_invalid_message(prefix: str) -> str:
    return (
        "Invalid endpoint. Example:\n"
        f"{prefix}set endpoint southeastasia\n"
        f"or {prefix}set endpoint southeastasia.tts.speech.microsoft.com"
    )


def build_api_key_verify_no_models_message(masked_key: str) -> str:
    return (
        f"api_key set to: {masked_key}\n"
        "Cannot verify key (no model list returned). Please check base_url."
    )


def build_api_key_verify_failed_message(masked_key: str) -> str:
    return (
        f"api_key set to: {masked_key}\n"
        "Cannot verify key. Please check base_url and api_key."
    )


def build_provider_save_hint_message(prefix: str) -> str:
    return f"Use {prefix}set provider save <name> to save a configuration first."


def build_provider_no_saved_message(prefix: str) -> str:
    return (
        "No saved provider configurations.\n\n"
        "Usage:\n"
        f"{prefix}set provider save <name> - save current API config\n"
        f"{prefix}set provider load <name> - load saved config\n"
        f"{prefix}set provider delete <name> - delete saved config"
    )


def build_provider_usage_message(prefix: str) -> str:
    return (
        "Usage:\n"
        f"{prefix}set provider list\n"
        f"{prefix}set provider save <name>\n"
        f"{prefix}set provider load <name>\n"
        f"{prefix}set provider delete <name>"
    )


def build_provider_list_usage_message(prefix: str) -> str:
    return (
        "\nUsage:\n"
        f"{prefix}set provider save <name>\n"
        f"{prefix}set provider load <name>\n"
        f"{prefix}set provider delete <name>"
    )


def build_provider_not_found_available_message(name: str, available: str) -> str:
    return (
        f"Provider '{name}' does not exist.\n"
        f"Available: {available}"
    )


def build_unknown_set_key_message(key: str) -> str:
    return (
        f"Unknown key: {key}\n\n"
        f"Available keys: {', '.join(SET_COMMAND_KEYS)}"
    )


def build_analyze_uploaded_files_message() -> str:
    return "Please analyze the uploaded files."
