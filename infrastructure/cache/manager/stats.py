"""Runtime statistics over cached data."""

from __future__ import annotations


class StatsMixin:
    def runtime_stats(self) -> dict:
        with self._lock:
            users = {key[0] for key in self._persona_tokens_cache}
            sessions = len(self._conversations_cache)
            messages = 0
            approx_bytes = 0
            for msgs in self._conversations_cache.values():
                messages += len(msgs)
                for m in msgs:
                    content = m.get("content")
                    if isinstance(content, str):
                        approx_bytes += len(content)
            cron_tasks = sum(len(value) for value in self._cron_tasks_cache.values())
        return {
            "users": len(users),
            "sessions": sessions,
            "messages": messages,
            "cron_tasks": cron_tasks,
            "approx_conversation_bytes": approx_bytes,
        }
