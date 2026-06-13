"""/stop, /update, /restart commands — runtime lifecycle."""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from services import run_hot_update, run_safe_restart, schedule_process_restart
from services.queue import cancel_user_responses
from services.refresh import ensure_user_state
from telegram_bot.handlers.common import get_log_context

from .context import TelegramCommandContextAdapter

logger = logging.getLogger(__name__)


async def _stop(ctx, *, platform: str) -> None:
    cancelled = cancel_user_responses(ctx.local_chat_id, ctx.local_user_id, platform=platform)
    await ctx.reply_text(f"Stopped {len(cancelled)} active response(s)." if cancelled else "No active responses to stop.")


async def _update(ctx, command_prefix: str) -> None:
    await ctx.reply_text("Starting hot update: fetching latest code...")
    result = await asyncio.to_thread(run_hot_update)
    if not result.get("ok"):
        await ctx.reply_text(f"Update failed:\n{result.get('message')}")
        return
    if not result.get("changed"):
        await ctx.reply_text(result.get("message") or "Already up to date.")
        return
    await ctx.reply_text(
        "Update applied successfully.\n"
        f"Branch: {result.get('branch')}\n"
        f"Commit: {result.get('old', '')[:7]} -> {result.get('new', '')[:7]}\n"
        "Restarting bot processes now..."
    )
    schedule_process_restart()


async def _restart(ctx) -> None:
    await ctx.reply_text("Syncing runtime state before restart...")
    result = await asyncio.to_thread(run_safe_restart)
    if not result.get("ok"):
        await ctx.reply_text(f"Restart cancelled:\n{result.get('message')}")
        return
    await ctx.reply_text("State synced. Restarting bot processes now...")
    schedule_process_restart()


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /stop", get_log_context(update))
    await _stop(TelegramCommandContextAdapter(update, context), platform="telegram")


async def update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /update", get_log_context(update))
    await _update(TelegramCommandContextAdapter(update, context), "/")


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /restart", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    await _restart(TelegramCommandContextAdapter(update, context))
