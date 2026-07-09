"""Cron task infrastructure.cache mixin."""

from __future__ import annotations

from infrastructure.config import MAX_CRON_TASKS_PER_USER


class CronMixin:
    def get_cron_tasks(self, user_id: int) -> list[dict]:
        with self._lock:
            return self._cron_tasks_cache.get(user_id, [])

    def get_all_cron_tasks(self) -> list[dict]:
        with self._lock:
            tasks = []
            for user_tasks in self._cron_tasks_cache.values():
                tasks.extend(user_tasks)
            return tasks

    def add_cron_task(self, user_id: int, name: str, cron_expression: str, prompt: str) -> dict | None:
        with self._lock:
            tasks = self._cron_tasks_cache.setdefault(user_id, [])
            if len(tasks) >= MAX_CRON_TASKS_PER_USER or any(t["name"] == name for t in tasks):
                return None
            task = {"id": None, "user_id": user_id, "name": name, "cron_expression": cron_expression, "prompt": prompt, "enabled": True, "last_run_at": None}
            tasks.append(task)
            self._new_cron_tasks.append(task)
            return task

    def delete_cron_task(self, user_id: int, name: str) -> bool:
        with self._lock:
            tasks = self._cron_tasks_cache.get(user_id, [])
            for index, task in enumerate(tasks):
                if task["name"] == name:
                    tasks.pop(index)
                    self._deleted_cron_tasks.append((user_id, name))
                    return True
            return False

    def update_cron_task(self, user_id: int, name: str, **kwargs) -> bool:
        with self._lock:
            for task in self._cron_tasks_cache.get(user_id, []):
                if task["name"] != name:
                    continue
                for key, value in kwargs.items():
                    if key in ("cron_expression", "prompt", "enabled"):
                        task[key] = value
                self._updated_cron_tasks.append(task)
                return True
            return False

    def update_cron_last_run(self, user_id: int, name: str, last_run_at) -> None:
        with self._lock:
            for task in self._cron_tasks_cache.get(user_id, []):
                if task["name"] == name:
                    task["last_run_at"] = last_run_at
                    self._updated_cron_tasks.append(task)
                    return

    def set_cron_tasks(self, user_id: int, tasks: list[dict]) -> None:
        with self._lock:
            self._cron_tasks_cache[user_id] = tasks
