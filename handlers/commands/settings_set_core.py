"""Core `/set` key handlers for API/model/prompt/temperature."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update

from services import update_user_setting
from .settings_models import fetch_models
from .settings_utils import mask_api_key, truncate_display
from utils.platform_parity import (
    build_api_key_verify_failed_message,
    build_api_key_verify_no_models_message,
    build_prompt_per_persona_message,
)

logger = logging.getLogger(__name__)


async def handle_set_core(
    update: Update,
    *,
    user_id: int,
    ctx: str,
    key: str,
    value: str,
) -> bool:
    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        logger.info("%s set base_url = %s", ctx, value)
        await update.message.reply_text(f"base_url set to: {value}")
        return True

    if key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = mask_api_key(value)
        logger.info("%s set api_key = %s", ctx, masked)
        try:
            models = await asyncio.get_event_loop().run_in_executor(None, lambda: fetch_models(user_id))
            if models:
                await update.message.reply_text(f"api_key set to: {masked}\nVerified ({len(models)} models available)")
            else:
                await update.message.reply_text(build_api_key_verify_no_models_message(masked))
        except Exception:
            await update.message.reply_text(build_api_key_verify_failed_message(masked))
        return True

    if key == "model":
        update_user_setting(user_id, "model", value)
        logger.info("%s set model = %s", ctx, value)
        await update.message.reply_text(f"model set to: {value}")
        return True

    if key == "prompt":
        await update.message.reply_text(build_prompt_per_persona_message("/"))
        return True

    if key == "global_prompt":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "global_prompt", "")
            logger.info("%s cleared global_prompt", ctx)
            await update.message.reply_text("global_prompt cleared.\nNow personas will use their own system prompts only.")
            return True
        update_user_setting(user_id, "global_prompt", val)
        logger.info("%s set global_prompt = %s", ctx, truncate_display(val, 50))
        await update.message.reply_text(
            f"global_prompt set to: {truncate_display(val, 100)}\n\n"
            "This prompt will be prepended to all personas' system prompts.\n"
            "Use /set global_prompt clear to remove."
        )
        return True

    if key != "temperature":
        return False
    try:
        temp = float(value)
        if 0.0 <= temp <= 2.0:
            update_user_setting(user_id, "temperature", temp)
            logger.info("%s set temperature = %s", ctx, temp)
            await update.message.reply_text(f"temperature set to: {temp}")
        else:
            await update.message.reply_text("Temperature must be between 0.0 and 2.0")
    except ValueError:
        await update.message.reply_text("Invalid temperature value")
    return True
