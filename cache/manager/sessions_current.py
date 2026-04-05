"""Current-session accessors mixin."""

from __future__ import annotations


class SessionsCurrentMixin:
    def get_current_session_id(self, user_id: int, persona_name: str = None) -> int | None:
        persona = persona_name or self.get_current_persona_name(user_id)
        with self._lock:
            data = self._personas_cache.get(user_id, {}).get(persona)
            return data.get("current_session_id") if data else None

    def set_current_session_id(self, user_id: int, persona_name: str, session_id: int | None) -> None:
        with self._lock:
            persona = self._personas_cache.get(user_id, {}).get(persona_name)
            if not persona:
                return
            persona["current_session_id"] = session_id
            self._dirty_personas.add((user_id, persona_name))

    def ensure_session_id(self, user_id: int, persona_name: str = None) -> int:
        persona = persona_name or self.get_current_persona_name(user_id)
        session_id = self.get_current_session_id(user_id, persona)
        if session_id is not None and self.get_session_by_id(session_id) is not None:
            return session_id
        sessions = self.get_sessions(user_id, persona)
        session_id = sessions[-1]["id"] if sessions else self.create_session(user_id, persona)["id"]
        self.set_current_session_id(user_id, persona, session_id)
        return session_id
