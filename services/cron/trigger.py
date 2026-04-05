"""Manual cron task trigger entrypoint."""

from __future__ import annotations

import threading

from cache.manager import cache

from .execution import _execute_cron_task
from .state import get_bot_ref


def run_cron_task(user_id: int, task_name: str) -> str:
    bot_ref = get_bot_ref()
    if bot_ref is None:
        return "Error: Bot is not initialized yet."

    tasks = cache.get_cron_tasks(user_id)
    task = next((t for t in tasks if t["name"] == task_name), None)
    if task is None:
        return f"Error: Task '{task_name}' not found."

    thread = threading.Thread(
        target=_execute_cron_task,
        args=(bot_ref, task),
        daemon=True,
    )
    thread.start()
    return f"Task '{task_name}' triggered. The result will be sent as a separate message."
