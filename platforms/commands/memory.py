"""Memory command handlers."""

from __future__ import annotations

from services import add_memory, clear_memories, delete_memory, get_memories
from utils.platform_parity import (
    build_forget_invalid_target_message,
    build_forget_usage_message,
    build_invalid_memory_number_message,
    build_memory_empty_message,
    build_memory_list_footer_message,
    build_remember_usage_message,
)


async def remember_command(ctx, *, command_prefix: str, content: str | None) -> None:
    if not content:
        await ctx.reply_text(build_remember_usage_message(command_prefix))
        return
    add_memory(ctx.local_user_id, content, source="user")
    await ctx.reply_text(f"Remembered: {content}")


async def memories_command(ctx, *, command_prefix: str) -> None:
    memories = get_memories(ctx.local_user_id)
    if not memories:
        await ctx.reply_text(build_memory_empty_message(command_prefix))
        return
    lines = ["Your memories:\n"]
    for index, memory in enumerate(memories, 1):
        source_tag = "[AI]" if memory["source"] == "ai" else "[user]"
        lines.append(f"{index}. {source_tag} {memory['content']}")
    lines.append(build_memory_list_footer_message(command_prefix))
    await ctx.reply_text("\n".join(lines))


async def forget_command(ctx, *, command_prefix: str, target: str | None) -> None:
    user_id = ctx.local_user_id
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
