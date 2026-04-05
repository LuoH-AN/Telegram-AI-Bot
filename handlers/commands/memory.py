"""Memory command wrappers backed by shared command core."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context
from platforms.commands.memory import forget_command as core_forget_command
from platforms.commands.memory import memories_command as core_memories_command
from platforms.commands.memory import remember_command as core_remember_command

from .context_adapter import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /remember", get_log_context(update))
    content = " ".join(context.args or []) or None
    await core_remember_command(TelegramCommandContextAdapter(update, context), command_prefix="/", content=content)


async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /memories", get_log_context(update))
    await core_memories_command(TelegramCommandContextAdapter(update, context), command_prefix="/")


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = (context.args or [None])[0]
    logger.info("%s /forget %s", get_log_context(update), target or "")
    await core_forget_command(TelegramCommandContextAdapter(update, context), command_prefix="/", target=target)
