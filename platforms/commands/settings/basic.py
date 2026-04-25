"""Core `/set` key handlers (base_url/api_key/model/prompt)."""

from __future__ import annotations

import asyncio

from services import update_user_setting
from services.platform import fetch_models_for_user, mask_key
from utils.platform_parity import (
    build_api_key_verify_failed_message,
    build_api_key_verify_no_models_message,
    build_prompt_per_persona_message,
)


async def handle_set_core(ctx, *, user_id: int, key: str, value: str, command_prefix: str) -> bool:
    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        await ctx.reply_text(f"base_url set to: {value}")
        return True
    if key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = mask_key(value)
        try:
            models = await asyncio.get_running_loop().run_in_executor(None, lambda: fetch_models_for_user(user_id))
            if models:
                await ctx.reply_text(f"api_key set to: {masked}\nVerified ({len(models)} models available)")
            else:
                await ctx.reply_text(build_api_key_verify_no_models_message(masked))
        except Exception:
            await ctx.reply_text(build_api_key_verify_failed_message(masked))
        return True
    if key == "model":
        update_user_setting(user_id, "model", value)
        await ctx.reply_text(f"model set to: {value}")
        return True
    if key == "prompt":
        await ctx.reply_text(build_prompt_per_persona_message(command_prefix))
        return True
    if key == "global_prompt":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "global_prompt", "")
            await ctx.reply_text("global_prompt cleared.\nNow personas will use their own system prompts only.")
            return True
        update_user_setting(user_id, "global_prompt", val)
        display = val[:100] + ("..." if len(val) > 100 else "")
        await ctx.reply_text(f"global_prompt set to: {display}\n\nThis prompt will be prepended to all personas' system prompts.\nUse {command_prefix}set global_prompt clear to remove.")
        return True
    if key != "temperature":
        return False
    try:
        temp = float(value)
    except ValueError:
        await ctx.reply_text("Invalid temperature value")
        return True
    if not (0.0 <= temp <= 2.0):
        await ctx.reply_text("Temperature must be between 0.0 and 2.0")
        return True
    update_user_setting(user_id, "temperature", temp)
    await ctx.reply_text(f"temperature set to: {temp}")
    return True
