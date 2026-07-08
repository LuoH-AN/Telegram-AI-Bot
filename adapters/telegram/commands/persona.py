"""/persona command — persona management."""

from __future__ import annotations

from application.use_cases.persona import run_persona_command

from .registry import CommandContext, command


@command("persona", usage="persona <list|switch|new|delete|edit> [args]", help="manage personas", category="Persona")
async def persona_command(ctx: CommandContext) -> str:
    return run_persona_command(ctx.user_id, ctx.args, command_prefix="/")
