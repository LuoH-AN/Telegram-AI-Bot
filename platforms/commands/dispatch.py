"""Text-based command dispatcher for platforms without framework command routing."""

from __future__ import annotations

from utils.platform import build_help_message

from .account import export_command, usage_command, web_command
from .basic import clear_command, help_command, restart_command, settings_command, start_command, stop_command, update_command
from .login import login_command
from .memory import forget_command, memories_command, remember_command
from .chat import chat_command
from .persona import persona_command
from .settings import set_command
from core.plugins import dispatch_skill_command


async def dispatch_command(
    ctx,
    text: str,
    *,
    command_prefix: str,
    platform: str,
    show_model_list_cb=None,
) -> None:
    normalized = (text or "").strip()
    body = normalized[len(command_prefix):].strip() if normalized.startswith(command_prefix) else normalized
    if not body:
        await ctx.reply_text(build_help_message(command_prefix))
        return
    name, _, rest = body.partition(" ")
    command = name.lower().strip()
    args = rest.split() if rest else []
    if command == "start":
        await start_command(ctx, command_prefix)
        return
    if command == "help":
        await help_command(ctx, command_prefix)
        return
    if command == "clear":
        await clear_command(ctx)
        return
    if command == "stop":
        await stop_command(ctx, platform=platform)
        return
    if command == "update":
        await update_command(ctx, command_prefix)
        return
    if command == "restart":
        await restart_command(ctx)
        return
    if command == "settings":
        await settings_command(ctx, command_prefix)
        return
    if command == "set":
        await set_command(ctx, command_prefix, *args, show_model_list_cb=show_model_list_cb)
        return
    if command == "usage":
        await usage_command(ctx, args=args)
        return
    if command == "export":
        await export_command(ctx)
        return
    if command == "remember":
        await remember_command(ctx, command_prefix=command_prefix, content=rest or None)
        return
    if command == "memories":
        await memories_command(ctx, command_prefix=command_prefix)
        return
    if command == "forget":
        await forget_command(ctx, command_prefix=command_prefix, target=args[0] if args else None)
        return
    if command == "persona":
        await persona_command(ctx, command_prefix=command_prefix, args=args)
        return
    if command == "chat":
        await chat_command(ctx, command_prefix=command_prefix, args=args)
        return
    if command == "web":
        await web_command(ctx)
        return
    if command == "login":
        await login_command(ctx, command_prefix, args=args)
        return
    if command == "skill":
        reply = await dispatch_skill_command(ctx, args)
        await ctx.reply_text(reply)
        return
    if command == "groupmode":
        from platforms.onebot.commands.group_mode import groupmode_command
        await groupmode_command(ctx)
        return
    await ctx.reply_text(build_help_message(command_prefix))
