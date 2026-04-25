"""Detailed help section builders."""

from __future__ import annotations

from ..config import _build_set_key_lines


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
        f"{prefix}update - pull latest code and hot-restart bot processes\n"
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
