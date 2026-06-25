"""/status command — project status overview."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from domain.services import build_status_text
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text

from .registry import command

logger = logging.getLogger(__name__)


@command("status", help="view project status")
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /status", get_log_context(update))
    await reply_rich_text(update.effective_message, build_status_text(update.effective_user.id))
