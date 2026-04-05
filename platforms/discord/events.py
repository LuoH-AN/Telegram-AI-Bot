"""Discord bot events."""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from services.cron import set_main_loop, start_cron_scheduler

from .chat.process import process_chat_message
from .config import DISCORD_COMMAND_PREFIX, logger
from .context import discord_ctx
from .message.content import should_respond_in_channel
from .replies import send_ctx_reply


def register_events(bot: commands.Bot) -> None:
    cron_scheduler_started = False

    @bot.event
    async def on_ready() -> None:
        nonlocal cron_scheduler_started
        if bot.user:
            logger.info("Discord bot logged in as %s (%s)", bot.user, bot.user.id)
        if not cron_scheduler_started:
            set_main_loop(asyncio.get_running_loop())
            start_cron_scheduler(bot)
            cron_scheduler_started = True

    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        logger.warning("Command error: %s", error)
        await send_ctx_reply(ctx, f"Error: {error}")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        ctx = await bot.get_context(message)
        if ctx.valid:
            await bot.invoke(ctx)
            return
        if (message.content or "").strip().startswith(DISCORD_COMMAND_PREFIX):
            return
        if not await should_respond_in_channel(bot, message):
            return
        user_id = int(message.author.id)
        dctx = discord_ctx(message.guild.id if message.guild else None, message.channel.id, user_id)
        logger.info("%s chat message", dctx)
        await process_chat_message(bot, message)
