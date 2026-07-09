"""Settings infrastructure.cache mixin."""

from __future__ import annotations

from typing import Any

from infrastructure.config import get_default_settings


class SettingsMixin:
    def get_settings(self, user_id: int) -> dict:
        with self._lock:
            if user_id not in self._settings_cache:
                self._settings_cache[user_id] = get_default_settings()
                self._dirty_settings.add(user_id)
                self._ensure_default_persona(user_id)
            return self._settings_cache[user_id]

    def update_settings(self, user_id: int, key: str, value: Any) -> None:
        with self._lock:
            self.get_settings(user_id)[key] = value
            self._dirty_settings.add(user_id)

    def set_settings(self, user_id: int, settings: dict) -> None:
        with self._lock:
            self._settings_cache[user_id] = settings

    def get_current_persona_name(self, user_id: int) -> str:
        with self._lock:
            return self.get_settings(user_id).get("current_persona", "default")

    def set_current_persona(self, user_id: int, persona_name: str) -> None:
        self.update_settings(user_id, "current_persona", persona_name)
