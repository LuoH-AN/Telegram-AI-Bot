"""Chat command wrapper."""

from __future__ import annotations

from core.session import run_chat_command


async def chat_command(ctx, *, command_prefix: str, args: list[str]) -> None:
    await ctx.reply_text(
        run_chat_command(
            ctx.local_user_id,
            args,
            command_prefix=command_prefix,
        )
    )
