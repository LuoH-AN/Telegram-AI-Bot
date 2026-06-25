"""/stop, /update, /restart commands — runtime lifecycle."""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from domain.services import run_hot_update, run_safe_restart, schedule_process_restart
from domain.services.queue import cancel_user_responses
from domain.services.refresh import ensure_user_state
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.rich_text import reply_rich_text

from .registry import command

logger = logging.getLogger(__name__)


@command("stop", help="stop active response")
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /stop", get_log_context(update))
    cancelled = cancel_user_responses(
        int(update.effective_chat.id), int(update.effective_user.id), platform="telegram"
    )
    await reply_rich_text(
        update.effective_message,
        f"Stopped {len(cancelled)} active response(s)." if cancelled else "No active responses to stop.",
    )


@command("update", help="pull latest bot code")
async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /update", get_log_context(update))
    message = update.effective_message
    await reply_rich_text(message, "Starting hot update: fetching latest code...")
    result = await asyncio.to_thread(run_hot_update)
    if not result.get("ok"):
        await reply_rich_text(message, f"Update failed:\n{result.get('message')}")
        return
    if not result.get("changed"):
        await reply_rich_text(message, result.get("message") or "Already up to date.")
        return
    await reply_rich_text(
        message,
        "Update applied successfully.\n"
        f"Branch: {result.get('branch')}\n"
        f"Commit: {result.get('old', '')[:7]} -> {result.get('new', '')[:7]}\n"
        "Restarting runtime now...",
    )
    schedule_process_restart()


@command("restart", help="restart bot processes safely")
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("%s /restart", get_log_context(update))
    await ensure_user_state(update.effective_user.id)
    message = update.effective_message
    await reply_rich_text(message, "Syncing runtime state before restart...")
    result = await asyncio.to_thread(run_safe_restart)
    if not result.get("ok"):
        await reply_rich_text(message, f"Restart cancelled:\n{result.get('message')}")
        return
    await reply_rich_text(message, "State synced. Restarting runtime now...")
    schedule_process_restart()
