"""Basic command handlers: /start, /help, /clear."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context
from utils.platform_parity import (
    build_help_message,
    build_start_message_missing_api,
    build_start_message_returning,
)

from services import (
    ensure_session,
    clear_conversation,
    get_current_persona_name,
    reset_token_usage,
    has_api_key,
)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - show different welcome messages based on user state."""
    user_id = update.effective_user.id
    ctx = get_log_context(update)
    logger.info("%s /start", ctx)

    if not has_api_key(user_id):
        await update.message.reply_text(build_start_message_missing_api("/"))
    else:
        persona = get_current_persona_name(user_id)
        await update.message.reply_text(build_start_message_returning(persona, "/"))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    logger.info("%s /help", get_log_context(update))
    await update.message.reply_text(build_help_message("/"))


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command - clear conversation history and reset usage for current persona."""
    user_id = update.effective_user.id
    persona_name = get_current_persona_name(user_id)
    ctx = get_log_context(update)
    logger.info("%s /clear (persona=%s)", ctx, persona_name)
    session_id = ensure_session(user_id, persona_name)
    clear_conversation(session_id)
    reset_token_usage(user_id)
    await update.message.reply_text(f"Conversation cleared and usage reset for persona '{persona_name}'.")
