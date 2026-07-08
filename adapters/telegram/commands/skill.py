"""/skill command — manage prompt-only skills."""

from __future__ import annotations

from infrastructure.tools.skills.commands import dispatch_skill_command

from .registry import CommandContext, command


@command("skill", usage="skill <list|install|remove|enable|disable|info> [args]", help="manage skills", category="Skills")
async def skill_command(ctx: CommandContext) -> str:
    return await dispatch_skill_command(ctx.user_id, ctx.args)
