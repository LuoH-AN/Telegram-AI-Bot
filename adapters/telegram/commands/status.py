"""/status command — project status overview."""

from __future__ import annotations

from domain.services import build_status_text
from adapters.telegram.ux.locale import language

from .registry import CommandContext, command


@command("status", help="view project status", category="System", refresh_state=False)
async def status_command(ctx: CommandContext) -> str:
    return build_status_text(ctx.user_id, lang=language(ctx.update, ctx.context))
