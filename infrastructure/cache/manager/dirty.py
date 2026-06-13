"""Dirty state access mixin."""

from __future__ import annotations


class DirtyMixin:
    _DIRTY_ATTRS = {
        "settings": ("_dirty_settings", "set"),
        "personas": ("_dirty_personas", "set"),
        "deleted_personas": ("_deleted_personas", "set"),
        "conversations": ("_dirty_conversations", "set"),
        "cleared_conversations": ("_cleared_conversations", "set"),
        "tokens": ("_dirty_tokens", "set"),
        "cleared_memories": ("_cleared_memories", "set"),
        "deleted_sessions": ("_deleted_sessions", "set"),
        "new_memories": ("_new_memories", "list"),
        "deleted_memory_ids": ("_deleted_memory_ids", "list"),
        "new_sessions": ("_new_sessions", "list"),
        "new_cron_tasks": ("_new_cron_tasks", "list"),
        "updated_cron_tasks": ("_updated_cron_tasks", "list"),
        "deleted_cron_tasks": ("_deleted_cron_tasks", "list"),
        "new_skills": ("_new_skills", "list"),
        "updated_skills": ("_updated_skills", "list"),
        "deleted_skills": ("_deleted_skills", "list"),
        "updated_skill_states": ("_updated_skill_states", "list"),
        "dirty_session_titles": ("_dirty_session_titles", "dict"),
    }

    def get_and_clear_dirty(self) -> dict:
        with self._lock:
            result = {}
            for key, (attr_name, _) in self._DIRTY_ATTRS.items():
                attr = getattr(self, attr_name)
                result[key] = attr.copy()
                attr.clear()
        return result

    def restore_dirty(self, dirty: dict) -> None:
        with self._lock:
            for key, (attr_name, kind) in self._DIRTY_ATTRS.items():
                attr = getattr(self, attr_name)
                if kind == "set":
                    attr.update(dirty.get(key, set()))
                elif kind == "list":
                    attr.extend(dirty.get(key, []))
                else:
                    attr.update(dirty.get(key, {}))
