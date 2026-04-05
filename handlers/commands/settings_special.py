"""Specialized model setters shared by /set title_model and /set cron_model."""

from __future__ import annotations

import logging

from telegram import Update

from services import update_user_setting
from utils.platform_parity import build_provider_save_hint_message

logger = logging.getLogger(__name__)


async def handle_specialized_model_set(
    update: Update,
    *,
    user_id: int,
    settings: dict,
    ctx: str,
    key: str,
    value: str,
) -> None:
    val = value.strip()
    if not val or val.lower() in {"off", "clear", "none"}:
        update_user_setting(user_id, key, "")
        await update.message.reply_text(f"{key} cleared (will use current provider + model)")
        return

    update_user_setting(user_id, key, val)
    logger.info("%s set %s = %s", ctx, key, val)
    if ":" not in val:
        await update.message.reply_text(f"{key} set to: {val}\n(uses current provider's API)")
        return

    provider, model = val.split(":", 1)
    presets = settings.get("api_presets", {})
    found = any(name.lower() == provider.lower() for name in presets)
    if found:
        await update.message.reply_text(f"{key} set to: {val}\nProvider: {provider} | Model: {model}")
        return

    available = ", ".join(presets.keys()) if presets else "(none)"
    await update.message.reply_text(
        f"{key} set to: {val}\n"
        f"Provider '{provider}' not found in presets.\n"
        f"Available: {available}\n"
        f"{build_provider_save_hint_message('/')}"
    )
