"""Memory command handlers: /remember, /memories, /forget."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context

from services import (
    get_memories,
    add_memory,
    delete_memory,
    clear_memories,
)

logger = logging.getLogger(__name__)


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /remember command - add a memory."""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "Usage: /remember <content>\n\n"
            "Example: /remember I prefer concise answers"
        )
        return

    content = " ".join(context.args)
    add_memory(user_id, content, source="user")
    logger.info("%s /remember: %s", get_log_context(update), content[:80])

    await update.message.reply_text(f"Remembered: {content}")


async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /memories command - list all memories."""
    user_id = update.effective_user.id
    logger.info("%s /memories", get_log_context(update))
    memories = get_memories(user_id)

    if not memories:
        await update.message.reply_text(
            "No memories yet.\n\n"
            "Use /remember <content> to add a memory.\n"
            "AI can also add memories during conversations."
        )
        return

    lines = ["Your memories:\n"]
    for i, mem in enumerate(memories, 1):
        source_tag = "[AI]" if mem["source"] == "ai" else "[user]"
        lines.append(f"{i}. {source_tag} {mem['content']}")

    lines.append("\n[user] = added by you")
    lines.append("[AI] = added by AI")
    lines.append("\nUse /forget <number> to delete")
    lines.append("Use /forget all to clear all")

    await update.message.reply_text("\n".join(lines))


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /forget command - delete a memory."""
    user_id = update.effective_user.id
    ctx = get_log_context(update)

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/forget <number> - Delete specific memory\n"
            "/forget all - Clear all memories\n\n"
            "Use /memories to see the list with numbers."
        )
        return

    arg = context.args[0].lower()

    if arg == "all":
        count = clear_memories(user_id)
        logger.info("%s /forget all (%d memories)", ctx, count)
        if count > 0:
            await update.message.reply_text(f"Cleared {count} memories.")
        else:
            await update.message.reply_text("No memories to clear.")
        return

    try:
        index = int(arg)
        if delete_memory(user_id, index):
            logger.info("%s /forget #%d", ctx, index)
            await update.message.reply_text(f"Memory #{index} deleted.")
        else:
            await update.message.reply_text(
                f"Invalid memory number: {index}\n"
                "Use /memories to see the list."
            )
    except ValueError:
        await update.message.reply_text(
            "Please specify a number or 'all'.\n"
            "Example: /forget 1 or /forget all"
        )
