"""Settings command handlers: /settings and /set."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.settings import get_settings_view_text
from services import get_user_settings
from services.refresh import ensure_user_state
from handlers.common import get_log_context
from utils.platform_parity import build_unknown_set_key_message

from .settings_models import _build_model_keyboard
from .settings_no_value import handle_set_without_value
from .settings_set_core import handle_set_core
from .settings_set_runtime import handle_set_runtime

logger = logging.getLogger(__name__)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info("%s /settings", get_log_context(update))
    ensure_user_state(user_id)
    await update.message.reply_text(get_settings_view_text(user_id, command_prefix="/"))


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    ensure_user_state(user_id)
    settings = get_user_settings(user_id)
    ctx = get_log_context(update)
    args = list(context.args or [])
    logger.info("%s /set %s", ctx, " ".join(args)[:120] if args else "")

    if not args or len(args) < 2:
        await handle_set_without_value(update, context, user_id=user_id, settings=settings)
        return

    key = args[0].lower()
    value = " ".join(args[1:])
    if await handle_set_core(update, user_id=user_id, ctx=ctx, key=key, value=value):
        return
    if await handle_set_runtime(
        update,
        user_id=user_id,
        settings=settings,
        ctx=ctx,
        key=key,
        value=value,
        args=args,
    ):
        return
    await update.message.reply_text(build_unknown_set_key_message(key))


__all__ = ["settings_command", "set_command", "_build_model_keyboard"]
