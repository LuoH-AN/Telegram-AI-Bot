"""Runtime/control `/set` key handlers."""

from __future__ import annotations

from telegram import Message

from infrastructure.config import VALID_REASONING_EFFORTS
from domain.services import get_current_persona_name, set_token_limit, update_user_setting
from shared.utils.platform import build_show_thinking_help_message, build_stream_mode_help_message
from adapters.telegram.rich_text import reply_rich_text


async def handle_set_runtime(
    message: Message, *, user_id: int, settings: dict, key: str, value: str, command_prefix: str
) -> bool:
    if key == "reasoning_effort":
        val = value.strip().lower()
        if not val or val in {"off", "clear"}:
            update_user_setting(user_id, "reasoning_effort", "")
            await reply_rich_text(message, "reasoning_effort cleared (follow provider/model default).")
            return True
        if val not in VALID_REASONING_EFFORTS:
            await reply_rich_text(message, "Invalid reasoning_effort. Available: none, minimal, low, medium, high, xhigh.")
            return True
        update_user_setting(user_id, "reasoning_effort", val)
        await reply_rich_text(message, f"reasoning_effort set to: {val}")
        return True
    if key == "token_limit":
        try:
            limit = int(value)
        except ValueError:
            await reply_rich_text(message, "Invalid token limit value")
            return True
        if limit < 0:
            await reply_rich_text(message, "Token limit must be non-negative")
            return True
        persona_name = get_current_persona_name(user_id)
        set_token_limit(user_id, limit, persona_name)
        await reply_rich_text(
            message, f"Persona '{persona_name}' token_limit set to: {limit:,}" + (" (unlimited)" if limit == 0 else "")
        )
        return True
    if key == "stream_mode":
        mode = value.strip().lower()
        if mode in {"default", "time", "chars", "off"}:
            update_user_setting(user_id, "stream_mode", mode)
            await reply_rich_text(message, f"stream_mode set to: {mode}")
            return True
        if not mode or mode in {"clear", "none"}:
            update_user_setting(user_id, "stream_mode", "")
            await reply_rich_text(message, "stream_mode cleared (will use default mode)")
            return True
        await reply_rich_text(message, build_stream_mode_help_message(command_prefix, settings.get("stream_mode", "") or "default"))
        return True
    if key != "show_thinking":
        return False
    val = value.strip().lower()
    if val in {"on", "true", "1", "yes", "y"}:
        update_user_setting(user_id, "show_thinking", True)
        await reply_rich_text(message, "show_thinking enabled.")
    elif val in {"off", "false", "0", "no", "n", "clear"}:
        update_user_setting(user_id, "show_thinking", False)
        await reply_rich_text(message, "show_thinking disabled.")
    else:
        await reply_rich_text(message, build_show_thinking_help_message(command_prefix, "on" if settings.get("show_thinking") else "off"))
    return True
