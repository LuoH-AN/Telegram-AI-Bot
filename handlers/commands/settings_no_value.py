"""Handling `/set <key>` calls without a value."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.provider import show_provider_list
from .settings_models import show_model_list
from .settings_utils import truncate_display
from utils.platform_parity import (
    build_global_prompt_help_message,
    build_reasoning_effort_help_message,
    build_set_usage_message,
    build_show_thinking_help_message,
    build_stream_mode_help_message,
)


async def handle_set_without_value(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    settings: dict,
) -> bool:
    if not context.args:
        await update.message.reply_text(build_set_usage_message("/"))
        return True

    key = context.args[0].lower()
    if key == "model":
        await show_model_list(update, context)
        return True
    if key == "provider":
        await update.message.reply_text(show_provider_list(user_id, command_prefix="/"))
        return True
    if key == "stream_mode":
        current = settings.get("stream_mode", "") or "default"
        await update.message.reply_text(build_stream_mode_help_message("/", current))
        return True
    if key == "show_thinking":
        current = "on" if settings.get("show_thinking") else "off"
        await update.message.reply_text(build_show_thinking_help_message("/", current))
        return True
    if key == "reasoning_effort":
        current = settings.get("reasoning_effort", "") or "(provider/model default)"
        await update.message.reply_text(build_reasoning_effort_help_message("/", current))
        return True
    if key == "global_prompt":
        current = settings.get("global_prompt", "") or "(none)"
        await update.message.reply_text(
            build_global_prompt_help_message("/", truncate_display(current, 100))
        )
        return True

    await update.message.reply_text(build_set_usage_message("/"))
    return True
