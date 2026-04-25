"""Session storage mixin."""

from __future__ import annotations


class SessionsStoreMixin:
    def get_sessions(self, user_id: int, persona_name: str = None) -> list[dict]:
        persona = persona_name or self.get_current_persona_name(user_id)
        key = (user_id, persona)
        with self._lock:
            self._sessions_cache.setdefault(key, [])
            return [dict(s) for s in self._sessions_cache[key]]

    def set_sessions(self, user_id: int, persona_name: str, sessions: list[dict]) -> None:
        copies = [dict(s) for s in sessions]
        with self._lock:
            self._sessions_cache[(user_id, persona_name)] = copies
            for session in copies:
                self._conversations_cache.setdefault(session["id"], [])

    def replace_user_sessions(self, user_id: int, sessions_by_persona: dict[str, list[dict]]) -> None:
        with self._lock:
            keys = [key for key in self._sessions_cache if key[0] == user_id]
            old_ids = {session["id"] for key in keys for session in self._sessions_cache.get(key, [])}
            for key in keys:
                del self._sessions_cache[key]
            for session_id in old_ids:
                self._conversations_cache.pop(session_id, None)
            for persona_name, sessions in sessions_by_persona.items():
                copies = [dict(s) for s in sessions]
                self._sessions_cache[(user_id, persona_name)] = copies
                for session in copies:
                    self._conversations_cache.setdefault(session["id"], [])

    def create_session(self, user_id: int, persona_name: str = None, title: str = None) -> dict:
        persona = persona_name or self.get_current_persona_name(user_id)
        session = {"id": self._next_session_id(), "user_id": user_id, "persona_name": persona, "title": title, "created_at": None}
        key = (user_id, persona)
        with self._lock:
            self._sessions_cache.setdefault(key, []).append(dict(session))
            self._conversations_cache[session["id"]] = []
            self._new_sessions.append(dict(session))
        return dict(session)

    def delete_session(self, session_id: int, user_id: int, persona_name: str) -> None:
        key = (user_id, persona_name)
        with self._lock:
            sessions = self._sessions_cache.get(key, [])
            self._sessions_cache[key] = [s for s in sessions if s["id"] != session_id]
            self._conversations_cache.pop(session_id, None)
            self._deleted_sessions.add(session_id)
            self._dirty_conversations.discard(session_id)
            self._cleared_conversations.discard(session_id)

    def update_session_title(self, session_id: int, title: str) -> None:
        with self._lock:
            for sessions in self._sessions_cache.values():
                for session in sessions:
                    if session["id"] == session_id:
                        session["title"] = title
                        self._dirty_session_titles[session_id] = title
                        return

    def get_session_by_id(self, session_id: int) -> dict | None:
        with self._lock:
            for sessions in self._sessions_cache.values():
                for session in sessions:
                    if session["id"] == session_id:
                        return dict(session)
        return None
