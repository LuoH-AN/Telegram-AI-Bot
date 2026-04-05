"""Adapter that exposes WeChat-style command context on Discord."""

from __future__ import annotations

from pathlib import Path

import discord
from discord.ext import commands

from .replies import send_ctx_reply


class DiscordCommandContextAdapter:
    def __init__(self, ctx: commands.Context):
        self.ctx = ctx
        self.local_user_id = int(ctx.author.id)
        self.local_chat_id = int(ctx.channel.id)
        self.is_group = bool(ctx.guild)
        self.export_dir = "runtime/discord/exports"

    async def reply_text(self, text: str) -> None:
        await send_ctx_reply(self.ctx, text)

    async def reply_file(self, file_path: str | Path, *, caption: str = "") -> None:
        path = Path(file_path)
        await self.ctx.reply(
            caption or path.name,
            file=discord.File(path, filename=path.name),
            mention_author=False,
        )

    async def send_private_text(self, text: str) -> None:
        await self.ctx.author.send(text)
