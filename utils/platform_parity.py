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


def format_log_context(*, platform: str, user_id: int, scope: str, chat_id: int) -> str:
    return f"[platform={platform} user={user_id} scope={scope} chat={chat_id}]"


def build_start_message_missing_api(prefix: str) -> str:
    return (
        "Welcome to AI Bot! 👋\n\n"
        "To get started, set your API key:\n"
        f"{prefix}set api_key YOUR_API_KEY\n\n"
        "Optionally configure:\n"
        f"{prefix}set base_url <url> - Custom API endpoint\n"
        f"{prefix}set model <name> - Choose a model\n\n"
        "Voice options:\n"
        f"{prefix}set voice <name> - Default TTS voice\n"
        f"{prefix}set style <style> - Default TTS style\n\n"
        f"Type {prefix}help for all commands."
    )


def build_start_message_returning(persona: str, prefix: str) -> str:
    return (
        f"Welcome back! Current persona: {persona}\n\n"
        f"Send a text/image/file to chat, or use {prefix}help."
    )


def build_help_message(prefix: str) -> str:
    return (
        "AI Bot Help\n\n"
        "Send text, image, or file to chat with AI.\n"
        "In groups/servers: mention the bot or reply to a bot message.\n"
        "In private chats/DMs: direct chat works.\n\n"
        f"Commands ({prefix}):\n"
        f"{prefix}start\n"
        f"{prefix}help\n"
        f"{prefix}clear\n"
        f"{prefix}persona ...\n"
        f"{prefix}chat ...\n"
        f"{prefix}settings\n"
        f"{prefix}set <key> <value>\n"
        f"{prefix}export\n"
        f"{prefix}usage\n"
        f"{prefix}remember <text>\n"
        f"{prefix}memories\n"
        f"{prefix}forget <num|all>\n"
        f"{prefix}web"
    )


def build_api_key_required_message(prefix: str) -> str:
    return f"Please set your OpenAI API key first:\n{prefix}set api_key YOUR_API_KEY"


def build_token_limit_reached_message(prefix: str, persona_name: str) -> str:
    return (
        f"Persona '{persona_name}' reached its token limit.\n"
        f"Use {prefix}usage to check usage, or "
        f"{prefix}set token_limit <number> to adjust."
    )


def build_latex_guidance() -> str:
    return (
        "\n\nIMPORTANT: Avoid LaTeX delimiters ($...$ / $$...$$). "
        "Use plain text and Unicode math symbols instead (e.g., × ÷ √ π ≤ ≥)."
    )


def build_memory_empty_message(prefix: str) -> str:
    return (
        "No memories yet.\n\n"
        f"Use {prefix}remember <content> to add a memory.\n"
        "AI can also add memories during conversations."
    )


def build_forget_usage_message(prefix: str) -> str:
    return (
        "Usage:\n"
        f"{prefix}forget <number> - Delete specific memory\n"
        f"{prefix}forget all - Clear all memories\n\n"
        f"Use {prefix}memories to see the list with numbers."
    )


def build_usage_reset_message(persona_name: str) -> str:
    return f"Usage reset for persona '{persona_name}'."


def build_persona_new_usage_message(prefix: str) -> str:
    return (
        f"Usage: {prefix}persona new <name> [system prompt]\n\n"
        "Example:\n"
        f"{prefix}persona new coder You are a coding assistant."
    )


def build_persona_created_message(name: str, prefix: str) -> str:
    return (
        f"Created and switched to persona: {name}\n\n"
        f"Use {prefix}persona prompt <text> to set its system prompt."
    )


def build_persona_prompt_overview_message(name: str, prompt: str, prefix: str) -> str:
    return (
        f"Current persona: {name}\n\n"
        f"Prompt: {prompt}\n\n"
        f"Usage: {prefix}persona prompt <new prompt>"
    )


def build_persona_not_found_message(name: str, prefix: str) -> str:
    return f"Persona '{name}' not found. Use {prefix}persona new {name} to create it."


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
        f"No sessions for persona '{persona_name}'.\n"
        f"Send a message to create one automatically, or use {prefix}chat new"
    )


def build_chat_unknown_subcommand_message(prefix: str) -> str:
    return (
        "Unknown subcommand. Usage:\n\n"
        f"{prefix}chat - list sessions\n"
        f"{prefix}chat new [title] - new session\n"
        f"{prefix}chat <num> - switch session\n"
        f"{prefix}chat rename <title> - rename\n"
        f"{prefix}chat delete <num> - delete"
    )


def build_chat_commands_message(prefix: str) -> str:
    return (
        f"{prefix}chat <num> - switch\n"
        f"{prefix}chat new [title] - new session\n"
        f"{prefix}chat rename <title> - rename\n"
        f"{prefix}chat delete <num> - delete"
    )


def build_web_dashboard_message(url: str) -> str:
    return (
        "Open the Gemen dashboard:\n"
        f"{url}\n\n"
        "This link expires in 10 minutes."
    )


def build_web_dm_sent_message() -> str:
    return "Dashboard link sent to your DM."


def build_web_dm_failed_message() -> str:
    return "Could not send DM. Please open a private chat and allow DMs, then retry."


def build_retry_message() -> str:
    return "Error. Please retry."


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
        f"Use {prefix}memories to see the list."
    )


def build_set_usage_message(prefix: str) -> str:
    return (
        f"Usage: {prefix}set <key> <value>\n\n"
        "Available keys:\n"
        "- base_url\n"
        "- api_key\n"
        "- model (no value to browse list)\n"
        "- temperature\n"
        "- reasoning_effort (none/minimal/low/medium/high/xhigh)\n"
        "- token_limit (current persona)\n"
        "- global_prompt <text|clear>\n"
        "- title_model [provider:]model\n"
        "- cron_model [provider:]model\n"
        "- cron_tools <tool1,tool2,...>\n"
        "- stream_mode (default/time/chars)\n"
        "- voice\n"
        "- style\n"
        "- endpoint\n"
        "- tool <name> <on|off>\n"
        "- cron_tool <name> <on|off>\n"
        "- provider save/load/delete/list\n\n"
        f"For prompt, use {prefix}persona prompt <text>"
    )


def build_prompt_per_persona_message(prefix: str) -> str:
    return (
        "Prompts are now per-persona.\n"
        f"Use {prefix}persona prompt <text> to set the prompt for current persona."
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
        "Could not verify key (no models returned). Check your base_url."
    )


def build_api_key_verify_failed_message(masked_key: str) -> str:
    return (
        f"api_key set to: {masked_key}\n"
        "Could not verify key. Check your base_url and api_key."
    )


def build_provider_save_hint_message(prefix: str) -> str:
    return f"Use {prefix}set provider save <name> to save one first."


def build_provider_no_saved_message(prefix: str) -> str:
    return (
        "No saved providers.\n\n"
        "Usage:\n"
        f"{prefix}set provider save <name> - Save current API config\n"
        f"{prefix}set provider load <name> - Load a saved config\n"
        f"{prefix}set provider delete <name> - Delete a saved config"
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
        f"Provider '{name}' not found.\n"
        f"Available: {available}"
    )


def build_unknown_set_key_message(key: str) -> str:
    return (
        f"Unknown key: {key}\n\n"
        "Available keys: base_url, api_key, model, temperature, reasoning_effort, token_limit, global_prompt, "
        "title_model, cron_model, cron_tools, stream_mode, voice, style, endpoint, tool, cron_tool, provider"
    )


def build_analyze_uploaded_files_message() -> str:
    return "Please analyze the uploaded file(s)."
