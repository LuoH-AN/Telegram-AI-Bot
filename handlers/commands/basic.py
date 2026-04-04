"""Basic command handlers: /start, /help, /clear, /stop."""

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
from services.refresh import ensure_user_state
from services.runtime_queue import cancel_user_responses

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - show different welcome messages based on user state."""
    user_id = update.effective_user.id
    ctx = get_log_context(update)
    logger.info("%s /start", ctx)
    ensure_user_state(user_id)

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
    ensure_user_state(user_id)
    persona_name = get_current_persona_name(user_id)
    ctx = get_log_context(update)
    logger.info("%s /clear (persona=%s)", ctx, persona_name)
    session_id = ensure_session(user_id, persona_name)
    clear_conversation(session_id)
    reset_token_usage(user_id)
    await update.message.reply_text(f"Cleared conversation history and reset usage for persona '{persona_name}'.")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command - cancel all active AI responses for the user."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    ctx = get_log_context(update)
    logger.info("%s /stop", ctx)

    cancelled = cancel_user_responses(chat_id, user_id)
    if cancelled:
        logger.info("%s cancelled %d active response(s)", ctx, len(cancelled))
        await update.message.reply_text(f"Stopped {len(cancelled)} active response(s).")
    else:
        await update.message.reply_text("No active responses to stop.")
