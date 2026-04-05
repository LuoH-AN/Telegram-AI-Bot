"""Constants shared by platform-facing message builders."""

from __future__ import annotations

SHARED_TOOL_STATUS_MAP = {
    "web_search": "Searching...",
    "url_fetch": "Fetching page...",
    "save_memory": "Saving to memory...",
    "shell_exec": "Running command...",
    "cron_create": "Creating scheduled task...",
    "cron_list": "Listing scheduled tasks...",
    "cron_delete": "Deleting scheduled task...",
    "cron_run": "Running scheduled task...",
    "page_screenshot": "Taking screenshot...",
    "page_content": "Extracting page content...",
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
        "- provider - provider management (list/save/load/delete)"
    )
