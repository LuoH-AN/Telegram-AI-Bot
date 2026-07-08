"""/stop, /update, /restart commands — runtime lifecycle."""

from __future__ import annotations

import asyncio

from domain.services import run_hot_update, run_safe_restart, schedule_process_restart
from domain.services.queue import cancel_user_responses

from .registry import CommandContext, command


@command("stop", help="stop active response", category="Chat", refresh_state=False)
async def stop_command(ctx: CommandContext) -> str:
    cancelled = cancel_user_responses(ctx.chat_id, ctx.user_id, platform="telegram")
    return f"Stopped {len(cancelled)} active response(s)." if cancelled else "No active responses to stop."


@command("update", help="pull latest bot code", category="System", refresh_state=False)
async def update_command(ctx: CommandContext) -> str:
    await ctx.message.reply_text("Starting hot update: fetching latest code...")
    result = await asyncio.to_thread(run_hot_update)
    if not result.get("ok"):
        return f"Update failed:\n{result.get('message')}"
    if not result.get("changed"):
        return result.get("message") or "Already up to date."
    schedule_process_restart()
    return (
        "Update applied successfully.\n"
        f"Branch: {result.get('branch')}\n"
        f"Commit: {result.get('old', '')[:7]} -> {result.get('new', '')[:7]}\n"
        "Restarting runtime now..."
    )


@command("restart", help="restart bot processes safely", category="System")
async def restart_command(ctx: CommandContext) -> str:
    await ctx.message.reply_text("Syncing runtime state before restart...")
    result = await asyncio.to_thread(run_safe_restart)
    if not result.get("ok"):
        return f"Restart cancelled:\n{result.get('message')}"
    schedule_process_restart()
    return "State synced. Restarting runtime now..."
