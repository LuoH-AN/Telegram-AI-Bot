"""Runtime/control `/set` key handlers."""

from __future__ import annotations

import logging

from telegram import Update

from core.provider import run_provider_command
from config import VALID_REASONING_EFFORTS
from services import get_current_persona_name, set_token_limit, update_user_setting
from .settings_special import handle_specialized_model_set
from utils.platform_parity import build_stream_mode_help_message

logger = logging.getLogger(__name__)


async def handle_set_runtime(
    update: Update,
    *,
    user_id: int,
    settings: dict,
    ctx: str,
    key: str,
    value: str,
    args: list[str],
) -> bool:
    if key == "reasoning_effort":
        val = value.strip().lower()
        if not val or val in {"off", "clear"}:
            update_user_setting(user_id, "reasoning_effort", "")
            logger.info("%s cleared reasoning_effort", ctx)
            await update.message.reply_text("reasoning_effort cleared (follow provider/model default).")
            return True
        if val not in VALID_REASONING_EFFORTS:
            await update.message.reply_text("Invalid reasoning_effort. Available: none, minimal, low, medium, high, xhigh.")
            return True
        update_user_setting(user_id, "reasoning_effort", val)
        logger.info("%s set reasoning_effort = %s", ctx, val)
        await update.message.reply_text(f"reasoning_effort set to: {val}")
        return True

    if key == "token_limit":
        try:
            limit = int(value)
        except ValueError:
            await update.message.reply_text("Invalid token limit value")
            return True
        if limit < 0:
            await update.message.reply_text("Token limit must be non-negative")
            return True
        persona_name = get_current_persona_name(user_id)
        set_token_limit(user_id, limit, persona_name)
        logger.info("%s set token_limit = %s (persona=%s)", ctx, limit, persona_name)
        await update.message.reply_text(f"Persona '{persona_name}' token_limit set to: {limit:,}" + (" (unlimited)" if limit == 0 else ""))
        return True

    if key == "provider":
        logger.info("%s provider %s", ctx, " ".join(args[1:]) if len(args) > 1 else "list")
        await update.message.reply_text(run_provider_command(user_id, args[1:], command_prefix="/"))
        return True

    if key in {"title_model", "cron_model"}:
        await handle_specialized_model_set(update, user_id=user_id, settings=settings, ctx=ctx, key=key, value=value)
        return True

    if key == "stream_mode":
        val = value.strip().lower()
        if val in {"default", "time", "chars", "off"}:
            update_user_setting(user_id, "stream_mode", val)
            logger.info("%s set stream_mode = %s", ctx, val)
            mode_desc = {"default": "time + chars combined", "time": "update by time interval", "chars": "update by character interval", "off": "non-streaming (full response at once)"}
            await update.message.reply_text(f"stream_mode set to: {val} ({mode_desc.get(val, '')})\nApplies to both Telegram and Discord streaming output.")
            return True
        if not val or val in {"off", "clear", "none"}:
            update_user_setting(user_id, "stream_mode", "")
            await update.message.reply_text("stream_mode cleared (will use default mode)\nDefault mode: time + chars combined")
            return True
        current = settings.get("stream_mode", "") or "default"
        await update.message.reply_text(build_stream_mode_help_message("/", current))
        return True

    if key != "show_thinking":
        return False
    val = value.strip().lower()
    if val in {"on", "true", "1", "yes", "y"}:
        update_user_setting(user_id, "show_thinking", True)
        logger.info("%s set show_thinking = on", ctx)
        await update.message.reply_text("show_thinking enabled.")
    elif val in {"off", "false", "0", "no", "n", "clear"}:
        update_user_setting(user_id, "show_thinking", False)
        logger.info("%s set show_thinking = off", ctx)
        await update.message.reply_text("show_thinking disabled.")
    else:
        await update.message.reply_text("Usage: /set show_thinking <on|off>")
    return True
