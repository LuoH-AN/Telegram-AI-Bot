"""Cron scheduler daemon loop and public controls."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from cache.manager import cache

from .delivery import _detect_platform
from .execution import _execute_cron_task
from .matcher import _cron_matches
from .state import (
    CST,
    POLL_INTERVAL,
    running_tasks,
    running_tasks_lock,
    set_bot_ref,
    set_main_loop_ref,
)

logger = logging.getLogger(__name__)


def _scheduler_loop(bot) -> None:
    while True:
        time.sleep(POLL_INTERVAL)
        try:
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
                with running_tasks_lock:
                    if task_key in running_tasks:
                        continue
                    running_tasks.add(task_key)

                thread = threading.Thread(
                    target=_execute_cron_task,
                    args=(bot, task),
                    daemon=True,
                )
                thread.start()
        except Exception:
            logger.exception("Cron scheduler error")


def set_main_loop(loop) -> None:
    set_main_loop_ref(loop)


def start_cron_scheduler(bot) -> None:
    set_bot_ref(bot)
    thread = threading.Thread(target=_scheduler_loop, args=(bot,), daemon=True)
    thread.start()
    platform = _detect_platform(bot)
    logger.info(
        "Cron scheduler started (platform=%s, poll interval=%ds)",
        platform,
        POLL_INTERVAL,
    )
