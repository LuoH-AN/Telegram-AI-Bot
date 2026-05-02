"""Web command wrapper backed by shared command core."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from platforms.telegram.handlers.common import get_log_context
from platforms.commands.account import web_command as core_web_command

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /web", get_log_context(update))
    await core_web_command(TelegramCommandContextAdapter(update, context))
