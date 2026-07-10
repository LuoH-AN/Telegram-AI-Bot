"""Manual cron task trigger entrypoint."""

from __future__ import annotations

import threading

from infrastructure.cache.manager import cache

from .execution import _execute_cron_task
from .state import get_bot_ref, running_tasks, running_tasks_lock


def run_cron_task(user_id: int, task_name: str, *, lang: str = "en") -> str:
    bot_ref = get_bot_ref()
    if bot_ref is None:
        return "❌ 机器人尚未初始化。" if lang == "zh" else "❌ Error: Bot is not initialized yet."

    tasks = cache.get_cron_tasks(user_id)
    task = next((t for t in tasks if t["name"] == task_name), None)
    if task is None:
        return f"❌ 找不到任务 `{task_name}`。" if lang == "zh" else f"❌ Task `{task_name}` not found."

    task_key = (user_id, task_name)
    with running_tasks_lock:
        if task_key in running_tasks:
            return f"⏳ **任务 `{task_name}` 正在运行。**" if lang == "zh" else f"⏳ **Task `{task_name}` is already running.**"
        running_tasks.add(task_key)

    thread = threading.Thread(
        target=_execute_cron_task,
        args=(bot_ref, task),
        daemon=True,
    )
    thread.start()
    if lang == "zh":
        return f"✅ **任务 `{task_name}` 已启动。** 结果会通过单独消息发送。"
    return f"✅ **Task `{task_name}` triggered.** The result will be sent as a separate message."
