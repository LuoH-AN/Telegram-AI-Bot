"""Settings-related message builders."""

from __future__ import annotations

from ..config import SET_COMMAND_KEYS, _build_set_key_lines


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
        "Available values:\n- none\n- minimal\n- low\n- medium\n- high\n- xhigh\n\n"
        f"Use {prefix}set reasoning_effort clear to follow provider/model default."
    )


def build_global_prompt_help_message(prefix: str, current: str) -> str:
    return f"Current global_prompt: {current}\n\nUsage: {prefix}set global_prompt <prompt>\nUse {prefix}set global_prompt clear to remove."


def build_prompt_per_persona_message(prefix: str) -> str:
    return f"Prompts are now managed per persona.\nUse {prefix}persona prompt <text> to set prompt for current persona."


def build_unknown_set_key_message(key: str) -> str:
    return f"Unknown key: {key}\n\nAvailable keys: {', '.join(SET_COMMAND_KEYS)}"
