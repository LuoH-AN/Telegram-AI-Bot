"""Settings command wrappers backed by shared command core."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context
from platforms.commands.basic import settings_command as core_settings_command
from platforms.commands.settings import set_command as core_set_command
from services.refresh import ensure_user_state

from ..context import TelegramCommandContextAdapter
from .model import _build_model_keyboard, show_model_list

logger = logging.getLogger(__name__)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info("%s /settings", get_log_context(update))
    ensure_user_state(user_id)
    await core_settings_command(TelegramCommandContextAdapter(update, context), "/")


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    args = list(context.args or [])
    logger.info("%s /set %s", get_log_context(update), " ".join(args)[:120] if args else "")
    ensure_user_state(user_id)

    async def _show_model_list() -> None:
        await show_model_list(update, context)

    await core_set_command(
        TelegramCommandContextAdapter(update, context),
        "/",
        *args,
        show_model_list_cb=_show_model_list,
    )


__all__ = ["settings_command", "set_command", "_build_model_keyboard"]
