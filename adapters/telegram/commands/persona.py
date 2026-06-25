"""/persona command — persona management."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from application.use_cases.persona import run_persona_command
from domain.services.refresh import ensure_user_state
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text

from .registry import command

logger = logging.getLogger(__name__)


@command("persona", help="manage personas")
async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /persona %s", get_log_context(update), " ".join(args) if args else "")
    await ensure_user_state(update.effective_user.id)
    await reply_rich_text(
        update.effective_message,
        run_persona_command(update.effective_user.id, args, command_prefix="/"),
    )
