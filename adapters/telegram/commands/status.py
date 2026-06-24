"""/status command — project status overview."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from domain.services import build_status_text
from adapters.telegram.handlers.common import get_log_context

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def _status(ctx) -> None:
    await ctx.reply_text(build_status_text(ctx.session_user_id))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /status", get_log_context(update))
    await _status(TelegramCommandContextAdapter(update, context))
