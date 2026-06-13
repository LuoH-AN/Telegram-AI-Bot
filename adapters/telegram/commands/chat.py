"""/chat command — session management."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from application.use_cases.session import run_chat_command
from domain.services.refresh import ensure_user_state
from adapters.telegram.handlers.common import get_log_context

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /chat %s", get_log_context(update), " ".join(args) if args else "")
    await ensure_user_state(update.effective_user.id)
    ctx = TelegramCommandContextAdapter(update, context)
    await ctx.reply_text(await run_chat_command(ctx.session_user_id, args, command_prefix="/"))
