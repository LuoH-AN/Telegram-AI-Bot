"""Discord logging context helpers."""

from __future__ import annotations

from discord.ext import commands

from utils.platform_parity import format_log_context


def discord_ctx(guild_id: int | None, channel_id: int, user_id: int) -> str:
    if guild_id is None:
        return format_log_context(
            platform="discord",
            user_id=user_id,
            scope="private",
            chat_id=channel_id,
        )
    return format_log_context(
        platform="discord",
        user_id=user_id,
        scope="group",
        chat_id=channel_id,
    )


def discord_cmd_ctx(ctx: commands.Context) -> str:
    user_id = int(ctx.author.id)
    guild_id = ctx.guild.id if ctx.guild else None
    channel_id = ctx.channel.id
    return discord_ctx(guild_id, channel_id, user_id)
