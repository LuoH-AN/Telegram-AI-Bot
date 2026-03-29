"""Telegram /skill command handlers."""

from telegram import Update
from telegram.ext import ContextTypes

from services import handle_skill_command
from services.refresh import ensure_user_state


async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    ensure_user_state(user_id)
    args = context.args or []
    result = handle_skill_command(user_id, list(args), command_prefix="/skill")
    await update.message.reply_text(result)
