"""Chat command wrapper backed by shared command core."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context
from platforms.command_core.persona_chat import chat_command as core_chat_command
from services.refresh import ensure_user_state

from .context_adapter import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /chat %s", get_log_context(update), " ".join(args) if args else "")
    ensure_user_state(update.effective_user.id)
    await core_chat_command(TelegramCommandContextAdapter(update, context), command_prefix="/", args=args)
