"""Skill command wrapper backed by the plugin system."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from platforms.telegram.handlers.common import get_log_context
from plugins.core import dispatch_skill_command

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /skill %s", get_log_context(update), " ".join(args))
    ctx = TelegramCommandContextAdapter(update, context)
    reply = await dispatch_skill_command(ctx, args)
    await ctx.reply_text(reply)
