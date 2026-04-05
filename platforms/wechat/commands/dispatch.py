"""Command router for WeChat inbound slash-commands."""

from __future__ import annotations

from platforms.command_core.dispatch import dispatch_command as dispatch_command_core


async def dispatch_command(ctx, text: str) -> None:
    await dispatch_command_core(
        ctx,
        text,
        command_prefix=ctx.runtime.command_prefix,
        platform="wechat",
    )
