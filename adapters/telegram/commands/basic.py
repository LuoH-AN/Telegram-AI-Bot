"""/start, /help, /clear commands."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from domain.services import (
    clear_conversation,
    ensure_session,
    get_current_persona_name,
    has_api_key,
    reset_token_usage,
)
from domain.services.refresh import ensure_user_state
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text
from shared.utils.platform import (
    build_help_message,
    build_start_message_missing_api,
    build_start_message_returning,
)

from .registry import command, all_commands

logger = logging.getLogger(__name__)


@command("start", help="show welcome message")
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /start", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    user_id = update.effective_user.id
    message = update.effective_message
    if not has_api_key(user_id):
        await reply_rich_text(message, build_start_message_missing_api("/"))
        return
    await reply_rich_text(message, build_start_message_returning(get_current_persona_name(user_id), "/"))


@command("help", help="show this help")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /help", get_log_context(update))
    commands = [(c.usage, c.help) for c in all_commands()]
    await reply_rich_text(update.effective_message, build_help_message("/", commands))


@command("clear", help="clear conversation")
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /clear", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    user_id = update.effective_user.id
    persona_name = get_current_persona_name(user_id)
    clear_conversation(ensure_session(user_id, persona_name))
    reset_token_usage(user_id)
    await reply_rich_text(
        update.effective_message,
        f"Conversation cleared and usage reset for persona '{persona_name}'.",
    )
