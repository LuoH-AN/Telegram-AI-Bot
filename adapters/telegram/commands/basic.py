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
from shared.utils.platform import (
    build_help_message,
    build_start_message_missing_api,
    build_start_message_returning,
)

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def _start(ctx, command_prefix: str) -> None:
    user_id = ctx.session_user_id
    if not has_api_key(user_id):
        await ctx.reply_text(build_start_message_missing_api(command_prefix))
        return
    await ctx.reply_text(build_start_message_returning(get_current_persona_name(user_id), command_prefix))


async def _clear(ctx) -> None:
    user_id = ctx.session_user_id
    persona_name = get_current_persona_name(user_id)
    clear_conversation(ensure_session(user_id, persona_name))
    reset_token_usage(user_id)
    await ctx.reply_text(f"Conversation cleared and usage reset for persona '{persona_name}'.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /start", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    await _start(TelegramCommandContextAdapter(update, context), "/")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /help", get_log_context(update))
    await TelegramCommandContextAdapter(update, context).reply_text(build_help_message("/"))


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /clear", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    await _clear(TelegramCommandContextAdapter(update, context))
