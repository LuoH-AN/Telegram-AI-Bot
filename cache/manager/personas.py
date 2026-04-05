"""Persona cache mixin."""

from __future__ import annotations

from config import get_default_persona


class PersonasMixin:
    def _ensure_default_persona(self, user_id: int) -> None:
        self._personas_cache.setdefault(user_id, {})
        if "default" not in self._personas_cache[user_id]:
            default = get_default_persona()
            default["current_session_id"] = None
            self._personas_cache[user_id]["default"] = default
            with self._lock:
                self._dirty_personas.add((user_id, "default"))

    def get_personas(self, user_id: int) -> dict[str, dict]:
        self.get_settings(user_id)
        return self._personas_cache.get(user_id, {})

    def get_persona(self, user_id: int, persona_name: str) -> dict | None:
        return self.get_personas(user_id).get(persona_name)

    def get_current_persona(self, user_id: int) -> dict:
        persona = self.get_persona(user_id, self.get_current_persona_name(user_id))
        if persona:
            return persona
        self._ensure_default_persona(user_id)
        return self._personas_cache[user_id]["default"]

    def create_persona(self, user_id: int, name: str, system_prompt: str) -> bool:
        self.get_settings(user_id)
        if name in self._personas_cache.get(user_id, {}):
            return False
        self._personas_cache.setdefault(user_id, {})
        self._personas_cache[user_id][name] = {"name": name, "system_prompt": system_prompt, "current_session_id": None}
        with self._lock:
            self._dirty_personas.add((user_id, name))
        return True

    def update_persona_prompt(self, user_id: int, persona_name: str, prompt: str) -> bool:
        persona = self.get_persona(user_id, persona_name)
        if not persona:
            return False
        persona["system_prompt"] = prompt
        with self._lock:
            self._dirty_personas.add((user_id, persona_name))
        return True

    def delete_persona(self, user_id: int, persona_name: str) -> bool:
        if persona_name == "default" or persona_name not in self._personas_cache.get(user_id, {}):
            return False
        key = (user_id, persona_name)
        for session in self._sessions_cache.get(key, []):
            self._conversations_cache.pop(session["id"], None)
        del self._personas_cache[user_id][persona_name]
        self._sessions_cache.pop(key, None)
        self._persona_tokens_cache.pop(key, None)
        with self._lock:
            self._deleted_personas.add((user_id, persona_name))
            self._dirty_personas.discard((user_id, persona_name))
        if self.get_current_persona_name(user_id) == persona_name:
            self.set_current_persona(user_id, "default")
        return True

    def set_persona(self, user_id: int, persona: dict) -> None:
        self._personas_cache.setdefault(user_id, {})
        if "current_session_id" not in persona:
            persona["current_session_id"] = None
        self._personas_cache[user_id][persona["name"]] = persona

    def replace_user_personas(self, user_id: int, personas: list[dict]) -> None:
        replaced: dict[str, dict] = {}
        for persona in personas:
            p = dict(persona)
            if "name" not in p:
                continue
            p.setdefault("current_session_id", None)
            replaced[p["name"]] = p
        if "default" not in replaced:
            default = get_default_persona()
            default["current_session_id"] = None
            replaced["default"] = default
        with self._lock:
            self._personas_cache[user_id] = replaced
