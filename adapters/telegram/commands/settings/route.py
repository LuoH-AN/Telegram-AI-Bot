"""/settings and /set command entry points."""

from __future__ import annotations

from telegram.constants import ChatType

from adapters.telegram.rich_text import reply_rich_text
from adapters.telegram.ux.locale import language
from adapters.telegram.ux.panels import settings_panel
from domain.services.platform import build_settings_text

from ..registry import CommandContext, command
from .command import run_set
from .model import show_model_list


@command("settings", help="view settings", category="Settings")
async def settings_command(ctx: CommandContext) -> str:
    if ctx.update.effective_chat.type == ChatType.PRIVATE:
        text, keyboard = settings_panel(ctx.user_id, language(ctx.update, ctx.context))
        await reply_rich_text(ctx.message, text, reply_markup=keyboard)
        return ""
    return build_settings_text(ctx.user_id, command_prefix="/")


@command("set", usage="set <key> <value>", help="modify settings", category="Settings")
async def set_command(ctx: CommandContext) -> str:
    async def _show_model_list() -> None:
        await show_model_list(ctx.update, ctx.context)

    await run_set(
        ctx.message,
        ctx.user_id,
        ctx.args,
        command_prefix="/",
        show_model_list_cb=_show_model_list,
    )
    return ""
