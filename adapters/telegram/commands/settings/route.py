"""/settings and /set command entry points."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from domain.services.platform import build_settings_text
from domain.services.refresh import ensure_user_state
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text

from ..registry import command
from .command import run_set
from .model import show_model_list

logger = logging.getLogger(__name__)


@command("settings", help="view settings")
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /settings", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    await reply_rich_text(
        update.effective_message,
        build_settings_text(update.effective_user.id, command_prefix="/"),
    )


@command("set", usage="set <key> <value>", help="modify settings")
async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /set %s", get_log_context(update), " ".join(args)[:120] if args else "")
    await ensure_user_state(update.effective_user.id)

    async def _show_model_list() -> None:
        await show_model_list(update, context)

    await run_set(
        update.effective_message,
        update.effective_user.id,
        args,
        command_prefix="/",
        show_model_list_cb=_show_model_list,
    )
