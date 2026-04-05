"""Persona command handler."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.persona import run_persona_command
from handlers.common import get_log_context
from services.refresh import ensure_user_state

logger = logging.getLogger(__name__)


async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    args = list(context.args or [])
    ctx = get_log_context(update)
    logger.info("%s /persona %s", ctx, " ".join(args) if args else "")
    ensure_user_state(user_id)
    text = run_persona_command(user_id, args, command_prefix="/")
    await update.message.reply_text(text)
