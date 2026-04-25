"""Register Discord commands via shared command modules."""
from __future__ import annotations
from discord.ext import commands
from platforms.commands.account import export_command as core_export_command
from platforms.commands.account import usage_command as core_usage_command
from platforms.commands.account import web_command as core_web_command
from platforms.commands.basic import clear_command as core_clear_command
from platforms.commands.chat import chat_command as core_chat_command
from platforms.commands.basic import help_command as core_help_command
from platforms.commands.basic import restart_command as core_restart_command
from platforms.commands.basic import settings_command as core_settings_command
from platforms.commands.basic import start_command as core_start_command
from platforms.commands.basic import stop_command as core_stop_command
from platforms.commands.basic import update_command as core_update_command
from platforms.commands.login import login_command as core_login_command
from platforms.commands.memory import forget_command as core_forget_command
from platforms.commands.memory import memories_command as core_memories_command
from platforms.commands.memory import remember_command as core_remember_command
from platforms.commands.persona import persona_command as core_persona_command
from platforms.commands.settings import set_command as core_set_command
from .command_context import DiscordCommandContextAdapter
from .config import DISCORD_COMMAND_PREFIX
def register_commands(bot: commands.Bot) -> None:
    @bot.command(name="start")
    async def _start(ctx: commands.Context) -> None:
        await core_start_command(DiscordCommandContextAdapter(ctx), DISCORD_COMMAND_PREFIX)

    @bot.command(name="help")
    async def _help(ctx: commands.Context) -> None:
        await core_help_command(DiscordCommandContextAdapter(ctx), DISCORD_COMMAND_PREFIX)
    @bot.command(name="clear")
    async def _clear(ctx: commands.Context) -> None:
        await core_clear_command(DiscordCommandContextAdapter(ctx))
    @bot.command(name="stop")
    async def _stop(ctx: commands.Context) -> None:
        await core_stop_command(DiscordCommandContextAdapter(ctx), platform="discord")
    @bot.command(name="restart")
    async def _restart(ctx: commands.Context) -> None:
        await core_restart_command(DiscordCommandContextAdapter(ctx))
    @bot.command(name="update")
    async def _update(ctx: commands.Context) -> None:
        await core_update_command(DiscordCommandContextAdapter(ctx), DISCORD_COMMAND_PREFIX)
    @bot.command(name="settings")
    async def _settings(ctx: commands.Context) -> None:
        await core_settings_command(DiscordCommandContextAdapter(ctx), DISCORD_COMMAND_PREFIX)
    @bot.command(name="login")
    async def _login(ctx: commands.Context, *args: str) -> None:
        await core_login_command(DiscordCommandContextAdapter(ctx), DISCORD_COMMAND_PREFIX, args=list(args))
    @bot.command(name="set")
    async def _set(ctx: commands.Context, *args: str) -> None:
        await core_set_command(DiscordCommandContextAdapter(ctx), DISCORD_COMMAND_PREFIX, *args)
    @bot.command(name="usage")
    async def _usage(ctx: commands.Context, *args: str) -> None:
        await core_usage_command(DiscordCommandContextAdapter(ctx), args=list(args))
    @bot.command(name="export")
    async def _export(ctx: commands.Context) -> None:
        await core_export_command(DiscordCommandContextAdapter(ctx))
    @bot.command(name="remember")
    async def _remember(ctx: commands.Context, *, content: str | None = None) -> None:
        await core_remember_command(
            DiscordCommandContextAdapter(ctx),
            command_prefix=DISCORD_COMMAND_PREFIX,
            content=content,
        )
    @bot.command(name="memories")
    async def _memories(ctx: commands.Context) -> None:
        await core_memories_command(DiscordCommandContextAdapter(ctx), command_prefix=DISCORD_COMMAND_PREFIX)
    @bot.command(name="forget")
    async def _forget(ctx: commands.Context, target: str | None = None) -> None:
        await core_forget_command(
            DiscordCommandContextAdapter(ctx),
            command_prefix=DISCORD_COMMAND_PREFIX,
            target=target,
        )
    @bot.command(name="persona")
    async def _persona(ctx: commands.Context, *args: str) -> None:
        await core_persona_command(
            DiscordCommandContextAdapter(ctx),
            command_prefix=DISCORD_COMMAND_PREFIX,
            args=list(args),
        )
    @bot.command(name="chat")
    async def _chat(ctx: commands.Context, *args: str) -> None:
        await core_chat_command(
            DiscordCommandContextAdapter(ctx),
            command_prefix=DISCORD_COMMAND_PREFIX,
            args=list(args),
        )
    @bot.command(name="web")
    async def _web(ctx: commands.Context) -> None:
        await core_web_command(DiscordCommandContextAdapter(ctx))
