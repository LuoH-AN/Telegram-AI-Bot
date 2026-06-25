"""/remember, /memories, /forget commands."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from domain.services import add_memory, clear_memories, delete_memory, get_memories
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text
from shared.utils.platform import (
    build_forget_invalid_target_message,
    build_forget_usage_message,
    build_invalid_memory_number_message,
    build_memory_empty_message,
    build_memory_list_footer_message,
    build_remember_usage_message,
)

from .registry import command

logger = logging.getLogger(__name__)


@command("remember", usage="remember <text>", help="add memory")
async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /remember", get_log_context(update))
    content = " ".join(context.args or []) or None
    if not content:
        await reply_rich_text(update.effective_message, build_remember_usage_message("/"))
        return
    add_memory(update.effective_user.id, content, source="user")
    await reply_rich_text(update.effective_message, f"Remembered: {content}")


@command("memories", help="view memories")
async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /memories", get_log_context(update))
    memories = get_memories(update.effective_user.id)
    message = update.effective_message
    if not memories:
        await reply_rich_text(message, build_memory_empty_message("/"))
        return
    lines = ["Your memories:\n"]
    for index, memory in enumerate(memories, 1):
        source_tag = "[AI]" if memory["source"] == "infrastructure.ai" else "[user]"
        lines.append(f"{index}. {source_tag} {memory['content']}")
    lines.append(build_memory_list_footer_message("/"))
    await reply_rich_text(message, "\n".join(lines))


@command("forget", usage="forget <num|all>", help="delete memory")
async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = (context.args or [None])[0]
    logger.info("%s /forget %s", get_log_context(update), target or "")
    user_id = update.effective_user.id
    message = update.effective_message
    if not target:
        await reply_rich_text(message, build_forget_usage_message("/"))
        return
    if target.lower() == "all":
        count = clear_memories(user_id)
        await reply_rich_text(message, f"Cleared {count} memories." if count > 0 else "No memories to clear.")
        return
    try:
        index = int(target)
    except ValueError:
        await reply_rich_text(message, build_forget_invalid_target_message("/"))
        return
    if delete_memory(user_id, index):
        await reply_rich_text(message, f"Memory #{index} deleted.")
        return
    await reply_rich_text(message, build_invalid_memory_number_message(index, "/"))
