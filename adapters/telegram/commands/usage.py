"""/usage and /export commands."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from domain.services import export_to_markdown, get_current_persona_name, reset_token_usage
from domain.services.platform import build_usage_text
from domain.services.refresh import ensure_user_state
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text
from shared.utils.format import markdown_to_telegram_html
from shared.utils.platform import build_usage_reset_message

from .registry import command

logger = logging.getLogger(__name__)


@command("usage", help="view usage")
async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /usage %s", get_log_context(update), " ".join(args) if args else "")
    await ensure_user_state(update.effective_user.id)
    user_id = update.effective_user.id
    persona_name = get_current_persona_name(user_id)
    if args and args[0].lower() == "reset":
        reset_token_usage(user_id, persona_name)
        await reply_rich_text(update.effective_message, build_usage_reset_message(persona_name))
        return
    await reply_rich_text(update.effective_message, build_usage_text(user_id))


@command("export", help="export conversation")
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /export", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    user_id = update.effective_user.id
    persona_name = get_current_persona_name(user_id)
    file_buffer = export_to_markdown(user_id, persona_name)
    message = update.effective_message
    if file_buffer is None:
        await reply_rich_text(
            message,
            f"No conversation history to export in current session (persona: '{persona_name}').",
        )
        return
    filename = getattr(file_buffer, "name", None) or f"chat_export_{persona_name}.md"
    try:
        file_buffer.seek(0)
    except Exception:
        pass
    caption = markdown_to_telegram_html(f"Chat history export (Persona: {persona_name})") or None
    await message.reply_document(
        document=file_buffer,
        filename=filename,
        caption=caption,
        parse_mode=ParseMode.HTML,
    )
