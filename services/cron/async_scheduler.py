"""Async cron scheduler using asyncio."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from cache.manager import cache

from .delivery import _detect_platform
from .execution import _execute_cron_task
from .matcher import _cron_matches
from .state import CST, POLL_INTERVAL

if TYPE_CHECKING:
    from core.container import Container

logger = logging.getLogger(__name__)

# Global running tasks (shared with sync scheduler)
_running_tasks: set[tuple[int, str]] = set()
_running_tasks_lock = asyncio.Lock()


async def _scheduler_loop_async(bot, container: "Container | None" = None) -> None:
    """Async version of the cron scheduler loop."""
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            await _process_cron_tasks_async(bot, container)
        except Exception:
            logger.exception("Async cron scheduler error")


async def _process_cron_tasks_async(bot, container: "Container | None" = None) -> None:
    """Process all cron tasks asynchronously."""
    now = datetime.now(CST)
    tasks = cache.get_all_cron_tasks()

    for task in tasks:
        if not task.get("enabled", True):
            continue

        expr = task.get("cron_expression", "")
        if not _cron_matches(expr, now):
            continue

        last_run = task.get("last_run_at")
        if last_run and hasattr(last_run, "minute"):
            if (
                last_run.year == now.year
                and last_run.month == now.month
                and last_run.day == now.day
                and last_run.hour == now.hour
                and last_run.minute == now.minute
            ):
                continue

        task_key = (task["user_id"], task["name"])
        async with _running_tasks_lock:
            if task_key in _running_tasks:
                continue
            _running_tasks.add(task_key)

        # Fire async task
        asyncio.create_task(_execute_cron_task_async(bot, task, container))


async def _execute_cron_task_async(bot, task: dict, container: "Container | None" = None) -> None:
    """Execute a single cron task asynchronously."""
    user_id = task["user_id"]
    task_name = task["name"]
    task_key = (user_id, task_name)

    try:
        # Run sync execution in thread pool
        await asyncio.to_thread(_execute_cron_task, bot, task)
    except Exception as exc:
        logger.exception("[user=%d] async cron task '%s' failed", user_id, task_name)
    finally:
        async with _running_tasks_lock:
            _running_tasks.discard(task_key)


async def start_async_cron_scheduler(bot, container: "Container | None" = None) -> None:
    """Start the async cron scheduler.

    Args:
        bot: The bot instance (Telegram, WeChat, or OneBot runtime).
        container: Optional dependency injection container.
    """
    task = asyncio.create_task(_scheduler_loop_async(bot, container))
    platform = _detect_platform(bot)
    logger.info(
        "Async cron scheduler started (platform=%s, poll interval=%ds)",
        platform,
        POLL_INTERVAL,
    )
    return task
