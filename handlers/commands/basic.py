"""Basic command wrappers backed by shared command core."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context
from platforms.commands.basic import clear_command as core_clear_command
from platforms.commands.basic import help_command as core_help_command
from platforms.commands.basic import restart_command as core_restart_command
from platforms.commands.basic import start_command as core_start_command
from platforms.commands.basic import stop_command as core_stop_command
from platforms.commands.basic import update_command as core_update_command
from platforms.commands.login import login_command as core_login_command
from services.refresh import ensure_user_state

from .context_adapter import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /start", get_log_context(update))
    ensure_user_state(update.effective_user.id)
    await core_start_command(TelegramCommandContextAdapter(update, context), "/")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /help", get_log_context(update))
    await core_help_command(TelegramCommandContextAdapter(update, context), "/")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /clear", get_log_context(update))
    ensure_user_state(update.effective_user.id)
    await core_clear_command(TelegramCommandContextAdapter(update, context))


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /stop", get_log_context(update))
    await core_stop_command(TelegramCommandContextAdapter(update, context), platform="telegram")


async def update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /update", get_log_context(update))
    await core_update_command(TelegramCommandContextAdapter(update, context), "/")


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /restart", get_log_context(update))
    ensure_user_state(update.effective_user.id)
    await core_restart_command(TelegramCommandContextAdapter(update, context))


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /login %s", get_log_context(update), " ".join(args) if args else "")
    ensure_user_state(update.effective_user.id)
    await core_login_command(TelegramCommandContextAdapter(update, context), "/", args=args)
