"""/status command — project status overview."""

from __future__ import annotations

from domain.services import build_status_text

from .registry import CommandContext, command


@command("status", help="view project status", refresh_state=False)
async def status_command(ctx: CommandContext) -> str:
    return build_status_text(ctx.user_id)
