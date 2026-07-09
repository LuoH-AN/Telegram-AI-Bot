"""Token usage infrastructure.cache mixin."""

from __future__ import annotations

from infrastructure.config import get_default_token_usage


class TokensMixin:
    def get_token_usage(self, user_id: int, persona_name: str = None) -> dict:
        with self._lock:
            persona = persona_name or self.get_current_persona_name(user_id)
            key = (user_id, persona)
            if key not in self._persona_tokens_cache:
                self._persona_tokens_cache[key] = get_default_token_usage()
            return self._persona_tokens_cache[key]

    def add_token_usage(self, user_id: int, prompt_tokens: int, completion_tokens: int, persona_name: str = None) -> None:
        with self._lock:
            persona = persona_name or self.get_current_persona_name(user_id)
            usage = self.get_token_usage(user_id, persona)
            usage["prompt_tokens"] += prompt_tokens
            usage["completion_tokens"] += completion_tokens
            usage["total_tokens"] += prompt_tokens + completion_tokens
            self._last_turn_prompt[(user_id, persona)] = prompt_tokens
            self._dirty_tokens.add((user_id, persona))

    def get_last_turn_prompt(self, user_id: int, persona_name: str = None) -> int:
        """Prompt-token size of the most recent turn (context occupied this turn).
        In-memory only; not persisted. 0 if no turn recorded yet."""
        with self._lock:
            persona = persona_name or self.get_current_persona_name(user_id)
            return self._last_turn_prompt.get((user_id, persona), 0)

    def reset_token_usage(self, user_id: int, persona_name: str = None) -> None:
        with self._lock:
            persona = persona_name or self.get_current_persona_name(user_id)
            usage = self.get_token_usage(user_id, persona)
            usage.update({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    def reset_token_usage(self, user_id: int, persona_name: str = None) -> None:
        with self._lock:
            persona = persona_name or self.get_current_persona_name(user_id)
            usage = self.get_token_usage(user_id, persona)
            usage.update({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            self._dirty_tokens.add((user_id, persona))

    def set_token_usage(self, user_id: int, persona_name: str, usage: dict) -> None:
        with self._lock:
            self._persona_tokens_cache[(user_id, persona_name)] = usage

    def replace_user_token_usage(self, user_id: int, usage_by_persona: dict[str, dict]) -> None:
        with self._lock:
            for key in [k for k in self._persona_tokens_cache if k[0] == user_id]:
                del self._persona_tokens_cache[key]
            for persona_name, usage in usage_by_persona.items():
                merged = get_default_token_usage()
                merged.update({
                    "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
                    "completion_tokens": usage.get("completion_tokens", 0) or 0,
                    "total_tokens": usage.get("total_tokens", 0) or 0,
                    "token_limit": usage.get("token_limit", 0) or 0,
                })
                self._persona_tokens_cache[(user_id, persona_name)] = merged

    def get_token_limit(self, user_id: int, persona_name: str = None) -> int:
        with self._lock:
            return self.get_token_usage(user_id, persona_name).get("token_limit", 0)

    def set_token_limit(self, user_id: int, limit: int, persona_name: str = None) -> None:
        with self._lock:
            persona = persona_name or self.get_current_persona_name(user_id)
            self.get_token_usage(user_id, persona)["token_limit"] = limit
            self._dirty_tokens.add((user_id, persona))

    def get_total_tokens_all_personas(self, user_id: int) -> int:
        with self._lock:
            return sum(usage.get("total_tokens", 0) for key, usage in self._persona_tokens_cache.items() if key[0] == user_id)
