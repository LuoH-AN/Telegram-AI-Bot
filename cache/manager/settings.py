"""Settings cache mixin."""

from __future__ import annotations

from typing import Any

from config import get_default_settings


class SettingsMixin:
    def get_settings(self, user_id: int) -> dict:
        if user_id not in self._settings_cache:
            self._settings_cache[user_id] = get_default_settings()
            with self._lock:
                self._dirty_settings.add(user_id)
            self._ensure_default_persona(user_id)
        return self._settings_cache[user_id]

    def update_settings(self, user_id: int, key: str, value: Any) -> None:
        settings = self.get_settings(user_id)
        settings[key] = value
        with self._lock:
            self._dirty_settings.add(user_id)

    def set_settings(self, user_id: int, settings: dict) -> None:
        self._settings_cache[user_id] = settings

    def get_current_persona_name(self, user_id: int) -> str:
        return self.get_settings(user_id).get("current_persona", "default")

    def set_current_persona(self, user_id: int, persona_name: str) -> None:
        self.update_settings(user_id, "current_persona", persona_name)
