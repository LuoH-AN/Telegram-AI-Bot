"""/remember, /memories, /forget commands."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from domain.services import add_memory, clear_memories, delete_memory, get_memories
from adapters.telegram.handlers.common import get_log_context
from shared.utils.platform import (
    build_forget_invalid_target_message,
    build_forget_usage_message,
    build_invalid_memory_number_message,
    build_memory_empty_message,
    build_memory_list_footer_message,
    build_remember_usage_message,
)

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def _remember(ctx, *, command_prefix: str, content: str | None) -> None:
    if not content:
        await ctx.reply_text(build_remember_usage_message(command_prefix))
        return
    add_memory(ctx.session_user_id, content, source="user")
    await ctx.reply_text(f"Remembered: {content}")


async def _memories(ctx, *, command_prefix: str) -> None:
    memories = get_memories(ctx.session_user_id)
    if not memories:
        await ctx.reply_text(build_memory_empty_message(command_prefix))
        return
    lines = ["Your memories:\n"]
    for index, memory in enumerate(memories, 1):
        source_tag = "[AI]" if memory["source"] == "infrastructure.ai" else "[user]"
        lines.append(f"{index}. {source_tag} {memory['content']}")
    lines.append(build_memory_list_footer_message(command_prefix))
    await ctx.reply_text("\n".join(lines))


async def _forget(ctx, *, command_prefix: str, target: str | None) -> None:
    user_id = ctx.session_user_id
    if not target:
        await ctx.reply_text(build_forget_usage_message(command_prefix))
        return
    if target.lower() == "all":
        count = clear_memories(user_id)
        await ctx.reply_text(f"Cleared {count} memories." if count > 0 else "No memories to clear.")
        return
    try:
        index = int(target)
    except ValueError:
        await ctx.reply_text(build_forget_invalid_target_message(command_prefix))
        return
    if delete_memory(user_id, index):
        await ctx.reply_text(f"Memory #{index} deleted.")
        return
    await ctx.reply_text(build_invalid_memory_number_message(index, command_prefix))


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /remember", get_log_context(update))
    content = " ".join(context.args or []) or None
    await _remember(TelegramCommandContextAdapter(update, context), command_prefix="/", content=content)


async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /memories", get_log_context(update))
    await _memories(TelegramCommandContextAdapter(update, context), command_prefix="/")


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = (context.args or [None])[0]
    logger.info("%s /forget %s", get_log_context(update), target or "")
    await _forget(TelegramCommandContextAdapter(update, context), command_prefix="/", target=target)
