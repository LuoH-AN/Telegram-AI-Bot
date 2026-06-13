"""/usage and /export commands."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from services import export_to_markdown, get_current_persona_name, reset_token_usage
from services.platform import build_usage_text
from services.refresh import ensure_user_state
from telegram_bot.handlers.common import get_log_context
from utils.platform import build_usage_reset_message

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def _usage(ctx, *, args: list[str]) -> None:
    user_id = ctx.session_user_id
    persona_name = get_current_persona_name(user_id)
    if args and args[0].lower() == "reset":
        reset_token_usage(user_id, persona_name)
        await ctx.reply_text(build_usage_reset_message(persona_name))
        return
    await ctx.reply_text(build_usage_text(user_id))


async def _export(ctx) -> None:
    user_id = ctx.session_user_id
    persona_name = get_current_persona_name(user_id)
    file_buffer = export_to_markdown(user_id, persona_name)
    if file_buffer is None:
        await ctx.reply_text(f"No conversation history to export in current session (persona: '{persona_name}').")
        return
    filename = getattr(file_buffer, "name", None) or f"chat_export_{persona_name}.md"
    try:
        file_buffer.seek(0)
    except Exception:
        pass
    await ctx.reply_document_buffer(
        file_buffer, filename=filename, caption=f"Chat history export (Persona: {persona_name})"
    )


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /usage %s", get_log_context(update), " ".join(args) if args else "")
    await ensure_user_state(update.effective_user.id)
    await _usage(TelegramCommandContextAdapter(update, context), args=args)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /export", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    await _export(TelegramCommandContextAdapter(update, context))
