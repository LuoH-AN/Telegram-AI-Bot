"""/settings and /set command entry points."""

from __future__ import annotations

from domain.services.platform import build_settings_text

from ..registry import CommandContext, command
from .command import run_set
from .model import show_model_list


@command("settings", help="view settings", category="Settings")
async def settings_command(ctx: CommandContext) -> str:
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
