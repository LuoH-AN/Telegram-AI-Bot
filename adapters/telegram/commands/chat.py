"""/chat command — session management."""

from __future__ import annotations

from application.use_cases.session import run_chat_command

from .registry import CommandContext, command


@command("chat", usage="chat <list|switch|new|delete|rename> [args]", help="manage sessions")
async def chat_command(ctx: CommandContext) -> str:
    return await run_chat_command(ctx.user_id, ctx.args, command_prefix="/")
