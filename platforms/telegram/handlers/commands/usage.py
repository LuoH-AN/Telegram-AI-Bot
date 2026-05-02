"""Usage/export command wrappers backed by shared command core."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from platforms.telegram.handlers.common import get_log_context
from platforms.commands.account import export_command as core_export_command
from platforms.commands.account import usage_command as core_usage_command
from services.refresh import ensure_user_state

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /usage %s", get_log_context(update), " ".join(args) if args else "")
    ensure_user_state(update.effective_user.id)
    await core_usage_command(TelegramCommandContextAdapter(update, context), args=args)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /export", get_log_context(update))
    ensure_user_state(update.effective_user.id)
    await core_export_command(TelegramCommandContextAdapter(update, context))
