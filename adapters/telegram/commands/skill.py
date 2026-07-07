"""Skill command wrapper backed by the plugin system."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text
from infrastructure.tools.skills.commands import dispatch_skill_command

from .registry import command

logger = logging.getLogger(__name__)


@command(
    "skill",
    usage="skill <list|install|remove|enable|disable|info>",
    help="manage skills",
)
async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = list(context.args or [])
    logger.info("%s /skill %s", get_log_context(update), " ".join(args))
    reply = await dispatch_skill_command(update.effective_user.id, args)
    await reply_rich_text(update.effective_message, reply)
