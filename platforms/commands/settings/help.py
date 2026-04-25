"""`/set <key>` without value handlers."""

from __future__ import annotations

import asyncio

from services import has_api_key
from services.platform import fetch_models_for_user
from utils.platform_parity import (
    build_api_key_required_message,
    build_global_prompt_help_message,
    build_reasoning_effort_help_message,
    build_set_usage_message,
    build_show_thinking_help_message,
    build_stream_mode_help_message,
)


async def handle_set_without_value(
    ctx,
    *,
    user_id: int,
    settings: dict,
    key: str,
    command_prefix: str,
    show_provider_list_cb,
    show_model_list_cb=None,
) -> bool:
    if key == "model":
        if show_model_list_cb is not None:
            await show_model_list_cb()
            return True
        if not has_api_key(user_id):
            await ctx.reply_text(build_api_key_required_message(command_prefix))
            return True
        models = await asyncio.get_running_loop().run_in_executor(None, lambda: fetch_models_for_user(user_id))
        if not models:
            await ctx.reply_text("Failed to fetch models. Check your API key and base_url.")
            return True
        head = models[:40]
        extra = f"\n...and {len(models) - 40} more" if len(models) > 40 else ""
        await ctx.reply_text("Available models:\n" + "\n".join(head) + extra)
        return True
    if key == "provider":
        await show_provider_list_cb()
        return True
    if key == "stream_mode":
        await ctx.reply_text(build_stream_mode_help_message(command_prefix, settings.get("stream_mode", "") or "default"))
        return True
    if key == "show_thinking":
        await ctx.reply_text(build_show_thinking_help_message(command_prefix, "on" if settings.get("show_thinking") else "off"))
        return True
    if key == "reasoning_effort":
        await ctx.reply_text(build_reasoning_effort_help_message(command_prefix, settings.get("reasoning_effort", "") or "(provider/model default)"))
        return True
    if key == "global_prompt":
        current = settings.get("global_prompt", "") or "(none)"
        display = current[:100] + ("..." if len(current) > 100 else "")
        await ctx.reply_text(build_global_prompt_help_message(command_prefix, display))
        return True
    await ctx.reply_text(build_set_usage_message(command_prefix))
    return True
