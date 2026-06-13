"""Persona command wrapper."""

from __future__ import annotations

from application.use_cases.persona import run_persona_command


async def persona_command(ctx, *, command_prefix: str, args: list[str]) -> None:
    await ctx.reply_text(
        run_persona_command(
            ctx.session_user_id,
            args,
            command_prefix=command_prefix,
        )
    )
