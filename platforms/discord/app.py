"""Discord app bootstrap."""

from __future__ import annotations

import threading

import discord
from discord.ext import commands

from cache import init_database
from services.platform_shared import start_web_server

from .commands import register_commands
from .config import DISCORD_BOT_TOKEN, DISCORD_COMMAND_PREFIX, logger
from .events import register_events
from .network import apply_discord_network_overrides


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    apply_discord_network_overrides()
    bot = commands.Bot(command_prefix=DISCORD_COMMAND_PREFIX, intents=intents, help_command=None)
    register_events(bot)
    register_commands(bot)
    return bot


def main() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables")
        return

    init_database()
    web_thread = threading.Thread(
        target=start_web_server,
        kwargs={"logger": logger},
        daemon=True,
    )
    web_thread.start()

    logger.info("Starting Discord bot...")
    create_bot().run(DISCORD_BOT_TOKEN)
