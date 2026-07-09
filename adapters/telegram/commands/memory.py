"""/remember, /memories, /forget commands."""

from __future__ import annotations

from domain.services import add_memory, clear_memories, delete_memory, get_memories
from shared.utils.platform import (
    build_forget_invalid_target_message,
    build_forget_usage_message,
    build_invalid_memory_number_message,
    build_memory_empty_message,
    build_memory_list_footer_message,
    build_remember_usage_message,
)

from .registry import CommandContext, command


@command("remember", usage="remember <text>", help="add memory", category="Memory")
async def remember_command(ctx: CommandContext) -> str:
    content = ctx.arg_text.strip() or None
    if not content:
        return build_remember_usage_message("/")
    add_memory(ctx.user_id, content, source="user")
    return f"Remembered: {content}"


@command("memories", help="view memories", category="Memory")
async def memories_command(ctx: CommandContext) -> str:
    memories = get_memories(ctx.user_id)
    if not memories:
        return build_memory_empty_message("/")
    lines = ["🧠 **Your memories:**\n"]
    for index, memory in enumerate(memories, 1):
        source_tag = "🤖" if memory["source"] == "infrastructure.ai" else "👤"
        lines.append(f"{index}. {source_tag} {memory['content']}")
    lines.append(build_memory_list_footer_message("/"))
    return "\n".join(lines)


@command("forget", usage="forget <num|all>", help="delete memory", category="Memory")
async def forget_command(ctx: CommandContext) -> str:
    target = ctx.args[0] if ctx.args else ""
    if not target:
        return build_forget_usage_message("/")
    if target.lower() == "all":
        count = clear_memories(ctx.user_id)
        return f"Cleared {count} memories." if count > 0 else "No memories to clear."
    try:
        index = int(target)
    except ValueError:
        return build_forget_invalid_target_message("/")
    if delete_memory(ctx.user_id, index):
        return f"Memory #{index} deleted."
    return build_invalid_memory_number_message(index, "/")
