"""/chat command — session management."""

from __future__ import annotations

from telegram.constants import ChatType

from adapters.telegram.rich_text import reply_rich_text
from adapters.telegram.ux.locale import language
from adapters.telegram.ux.panels import sessions_panel
from application.use_cases.session import run_chat_command

from .registry import CommandContext, command


@command("chat", usage="chat <list|switch|new|delete|rename> [args]", help="manage sessions", category="Chat")
async def chat_command(ctx: CommandContext) -> str:
    if not ctx.args and ctx.update.effective_chat.type == ChatType.PRIVATE:
        text, keyboard = sessions_panel(ctx.user_id, language(ctx.update, ctx.context))
        await reply_rich_text(ctx.message, text, reply_markup=keyboard)
        return ""
    return await run_chat_command(ctx.user_id, ctx.args, command_prefix="/")
