"""/persona command — persona management."""

from __future__ import annotations

from telegram.constants import ChatType

from adapters.telegram.rich_text import reply_rich_text
from adapters.telegram.ux.locale import language
from adapters.telegram.ux.panels import personas_panel
from application.use_cases.persona import run_persona_command

from .registry import CommandContext, command


@command("persona", usage="persona <list|switch|new|delete|prompt> [args]", help="manage personas", category="Persona")
async def persona_command(ctx: CommandContext) -> str:
    if not ctx.args and ctx.update.effective_chat.type == ChatType.PRIVATE:
        text, keyboard = personas_panel(ctx.user_id, language(ctx.update, ctx.context))
        await reply_rich_text(ctx.message, text, reply_markup=keyboard)
        return ""
    return await run_persona_command(ctx.user_id, ctx.args, command_prefix="/")
