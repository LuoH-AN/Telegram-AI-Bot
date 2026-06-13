"""Chat command wrapper."""

from __future__ import annotations

from application.use_cases.session import run_chat_command


async def chat_command(ctx, *, command_prefix: str, args: list[str]) -> None:
    await ctx.reply_text(
        await run_chat_command(
            ctx.session_user_id,
            args,
            command_prefix=command_prefix,
        )
    )
