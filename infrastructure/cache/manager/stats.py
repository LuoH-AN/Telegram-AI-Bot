"""Runtime statistics over cached data."""

from __future__ import annotations


class StatsMixin:
    def runtime_stats(self) -> dict:
        with self._lock:
            users = {key[0] for key in self._persona_tokens_cache}
            sessions = len(self._conversations_cache)
            messages = sum(len(value) for value in self._conversations_cache.values())
            cron_tasks = sum(len(value) for value in self._cron_tasks_cache.values())
        return {
            "users": len(users),
            "sessions": sessions,
            "messages": messages,
            "cron_tasks": cron_tasks,
        }
