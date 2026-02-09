"""In-memory cache manager."""

import logging
import threading
from typing import Any

from config import get_default_settings, get_default_persona, get_default_token_usage

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages in-memory caches for settings, personas, conversations, tokens, and memories."""

    def __init__(self):
        # Global settings per user
        self._settings_cache: dict[int, dict] = {}
        # Personas per user: {user_id: {persona_name: {name, system_prompt}}}
        self._personas_cache: dict[int, dict[str, dict]] = {}
        # Conversations per user per persona: {(user_id, persona_name): [messages]}
        self._conversations_cache: dict[tuple[int, str], list] = {}
        # Token usage per user per persona: {(user_id, persona_name): {tokens}}
        self._persona_tokens_cache: dict[tuple[int, str], dict] = {}
        # Memories per user (shared across personas)
        self._memories_cache: dict[int, list[dict]] = {}

        # Dirty flags for tracking what needs syncing
        self._dirty_settings: set[int] = set()
        self._dirty_personas: set[tuple[int, str]] = set()
        self._deleted_personas: set[tuple[int, str]] = set()
        self._dirty_conversations: set[tuple[int, str]] = set()
        self._cleared_conversations: set[tuple[int, str]] = set()
        self._dirty_tokens: set[tuple[int, str]] = set()
        self._new_memories: list[dict] = []
        self._deleted_memory_ids: list[int] = []
        self._cleared_memories: set[int] = set()

        self._lock = threading.Lock()

    # Settings cache methods
    def get_settings(self, user_id: int) -> dict:
        """Get global settings for a user, creating defaults if not exists."""
        if user_id not in self._settings_cache:
            self._settings_cache[user_id] = get_default_settings()
            with self._lock:
                self._dirty_settings.add(user_id)
            # Also create default persona
            self._ensure_default_persona(user_id)
        return self._settings_cache[user_id]

    def update_settings(self, user_id: int, key: str, value: Any) -> None:
        """Update a specific setting for a user."""
        settings = self.get_settings(user_id)
        settings[key] = value
        with self._lock:
            self._dirty_settings.add(user_id)

    def set_settings(self, user_id: int, settings: dict) -> None:
        """Set entire settings dict for a user (used during loading)."""
        self._settings_cache[user_id] = settings

    def get_current_persona_name(self, user_id: int) -> str:
        """Get the current persona name for a user."""
        return self.get_settings(user_id).get("current_persona", "default")

    def set_current_persona(self, user_id: int, persona_name: str) -> None:
        """Set the current persona for a user."""
        self.update_settings(user_id, "current_persona", persona_name)

    # Persona cache methods
    def _ensure_default_persona(self, user_id: int) -> None:
        """Ensure user has a default persona."""
        if user_id not in self._personas_cache:
            self._personas_cache[user_id] = {}
        if "default" not in self._personas_cache[user_id]:
            default = get_default_persona()
            self._personas_cache[user_id]["default"] = default
            with self._lock:
                self._dirty_personas.add((user_id, "default"))

    def get_personas(self, user_id: int) -> dict[str, dict]:
        """Get all personas for a user."""
        self.get_settings(user_id)  # Ensure initialized
        return self._personas_cache.get(user_id, {})

    def get_persona(self, user_id: int, persona_name: str) -> dict | None:
        """Get a specific persona."""
        personas = self.get_personas(user_id)
        return personas.get(persona_name)

    def get_current_persona(self, user_id: int) -> dict:
        """Get the current persona for a user."""
        name = self.get_current_persona_name(user_id)
        persona = self.get_persona(user_id, name)
        if not persona:
            # Fallback to default
            self._ensure_default_persona(user_id)
            return self._personas_cache[user_id]["default"]
        return persona

    def create_persona(self, user_id: int, name: str, system_prompt: str) -> bool:
        """Create a new persona. Returns False if already exists."""
        self.get_settings(user_id)  # Ensure initialized
        if name in self._personas_cache.get(user_id, {}):
            return False
        if user_id not in self._personas_cache:
            self._personas_cache[user_id] = {}
        self._personas_cache[user_id][name] = {
            "name": name,
            "system_prompt": system_prompt,
        }
        with self._lock:
            self._dirty_personas.add((user_id, name))
        return True

    def update_persona_prompt(self, user_id: int, persona_name: str, prompt: str) -> bool:
        """Update a persona's system prompt."""
        persona = self.get_persona(user_id, persona_name)
        if not persona:
            return False
        persona["system_prompt"] = prompt
        with self._lock:
            self._dirty_personas.add((user_id, persona_name))
        return True

    def delete_persona(self, user_id: int, persona_name: str) -> bool:
        """Delete a persona. Cannot delete 'default'."""
        if persona_name == "default":
            return False
        if user_id not in self._personas_cache:
            return False
        if persona_name not in self._personas_cache[user_id]:
            return False
        del self._personas_cache[user_id][persona_name]
        # Also clear conversations and tokens for this persona
        conv_key = (user_id, persona_name)
        self._conversations_cache.pop(conv_key, None)
        self._persona_tokens_cache.pop(conv_key, None)
        with self._lock:
            self._deleted_personas.add((user_id, persona_name))
            self._dirty_personas.discard((user_id, persona_name))
        # Switch to default if this was current
        if self.get_current_persona_name(user_id) == persona_name:
            self.set_current_persona(user_id, "default")
        return True

    def set_persona(self, user_id: int, persona: dict) -> None:
        """Set a persona (used during loading)."""
        if user_id not in self._personas_cache:
            self._personas_cache[user_id] = {}
        self._personas_cache[user_id][persona["name"]] = persona

    # Conversation cache methods (per persona)
    def get_conversation(self, user_id: int, persona_name: str = None) -> list:
        """Get conversation history for a user's persona."""
        if persona_name is None:
            persona_name = self.get_current_persona_name(user_id)
        key = (user_id, persona_name)
        if key not in self._conversations_cache:
            self._conversations_cache[key] = []
        return self._conversations_cache[key]

    def add_message(self, user_id: int, role: str, content: str, persona_name: str = None) -> None:
        """Add a message to conversation history."""
        if persona_name is None:
            persona_name = self.get_current_persona_name(user_id)
        key = (user_id, persona_name)
        if key not in self._conversations_cache:
            self._conversations_cache[key] = []
        self._conversations_cache[key].append({"role": role, "content": content})
        with self._lock:
            self._dirty_conversations.add(key)

    def clear_conversation(self, user_id: int, persona_name: str = None) -> None:
        """Clear conversation history for a persona."""
        if persona_name is None:
            persona_name = self.get_current_persona_name(user_id)
        key = (user_id, persona_name)
        self._conversations_cache[key] = []
        with self._lock:
            self._cleared_conversations.add(key)
            self._dirty_conversations.discard(key)

    def set_conversation(self, user_id: int, persona_name: str, messages: list) -> None:
        """Set entire conversation for a persona (used during loading)."""
        self._conversations_cache[(user_id, persona_name)] = messages

    # Token usage cache methods (per persona)
    def get_token_usage(self, user_id: int, persona_name: str = None) -> dict:
        """Get token usage for a persona."""
        if persona_name is None:
            persona_name = self.get_current_persona_name(user_id)
        key = (user_id, persona_name)
        if key not in self._persona_tokens_cache:
            self._persona_tokens_cache[key] = get_default_token_usage()
        return self._persona_tokens_cache[key]

    def add_token_usage(self, user_id: int, prompt_tokens: int, completion_tokens: int, persona_name: str = None) -> None:
        """Add token usage for a persona."""
        if persona_name is None:
            persona_name = self.get_current_persona_name(user_id)
        usage = self.get_token_usage(user_id, persona_name)
        usage["prompt_tokens"] += prompt_tokens
        usage["completion_tokens"] += completion_tokens
        usage["total_tokens"] += prompt_tokens + completion_tokens
        with self._lock:
            self._dirty_tokens.add((user_id, persona_name))

    def reset_token_usage(self, user_id: int, persona_name: str = None) -> None:
        """Reset token usage counters for a persona."""
        if persona_name is None:
            persona_name = self.get_current_persona_name(user_id)
        usage = self.get_token_usage(user_id, persona_name)
        usage["prompt_tokens"] = 0
        usage["completion_tokens"] = 0
        usage["total_tokens"] = 0
        with self._lock:
            self._dirty_tokens.add((user_id, persona_name))

    def set_token_usage(self, user_id: int, persona_name: str, usage: dict) -> None:
        """Set token usage for a persona (used during loading)."""
        self._persona_tokens_cache[(user_id, persona_name)] = usage

    def get_token_limit(self, user_id: int) -> int:
        """Get global token limit for a user."""
        return self.get_settings(user_id).get("token_limit", 0)

    def set_token_limit(self, user_id: int, limit: int) -> None:
        """Set global token limit for a user."""
        self.update_settings(user_id, "token_limit", limit)

    def get_total_tokens_all_personas(self, user_id: int) -> int:
        """Get total tokens across all personas for limit checking."""
        total = 0
        for key, usage in self._persona_tokens_cache.items():
            if key[0] == user_id:
                total += usage.get("total_tokens", 0)
        return total

    # Memory cache methods (shared across personas)
    def get_memories(self, user_id: int) -> list[dict]:
        """Get all memories for a user."""
        if user_id not in self._memories_cache:
            self._memories_cache[user_id] = []
        return self._memories_cache[user_id]

    def add_memory(self, user_id: int, content: str, source: str = "user", embedding: list[float] | None = None) -> dict:
        """Add a memory for a user."""
        if user_id not in self._memories_cache:
            self._memories_cache[user_id] = []
        memory = {
            "id": None,
            "user_id": user_id,
            "content": content,
            "source": source,
            "embedding": embedding,
        }
        self._memories_cache[user_id].append(memory)
        with self._lock:
            self._new_memories.append(memory)
        return memory

    def delete_memory(self, user_id: int, memory_index: int) -> bool:
        """Delete a memory by index (0-based)."""
        memories = self.get_memories(user_id)
        if 0 <= memory_index < len(memories):
            removed = memories.pop(memory_index)
            if removed.get("id") is not None:
                with self._lock:
                    self._deleted_memory_ids.append(removed["id"])
            return True
        return False

    def clear_memories(self, user_id: int) -> None:
        """Clear all memories for a user."""
        self._memories_cache[user_id] = []
        with self._lock:
            self._cleared_memories.add(user_id)

    def set_memories(self, user_id: int, memories: list[dict]) -> None:
        """Set entire memories list for a user (used during loading)."""
        self._memories_cache[user_id] = memories

    # Dirty tracking methods
    def get_and_clear_dirty(self) -> dict:
        """Get all dirty flags and clear them atomically."""
        with self._lock:
            result = {
                "settings": self._dirty_settings.copy(),
                "personas": self._dirty_personas.copy(),
                "deleted_personas": self._deleted_personas.copy(),
                "conversations": self._dirty_conversations.copy(),
                "cleared_conversations": self._cleared_conversations.copy(),
                "tokens": self._dirty_tokens.copy(),
                "new_memories": self._new_memories.copy(),
                "deleted_memory_ids": self._deleted_memory_ids.copy(),
                "cleared_memories": self._cleared_memories.copy(),
            }
            self._dirty_settings.clear()
            self._dirty_personas.clear()
            self._deleted_personas.clear()
            self._dirty_conversations.clear()
            self._cleared_conversations.clear()
            self._dirty_tokens.clear()
            self._new_memories.clear()
            self._deleted_memory_ids.clear()
            self._cleared_memories.clear()
        return result

    def restore_dirty(self, dirty: dict) -> None:
        """Restore dirty flags (used on sync failure)."""
        with self._lock:
            self._dirty_settings.update(dirty.get("settings", set()))
            self._dirty_personas.update(dirty.get("personas", set()))
            self._deleted_personas.update(dirty.get("deleted_personas", set()))
            self._dirty_conversations.update(dirty.get("conversations", set()))
            self._cleared_conversations.update(dirty.get("cleared_conversations", set()))
            self._dirty_tokens.update(dirty.get("tokens", set()))
            self._new_memories.extend(dirty.get("new_memories", []))
            self._deleted_memory_ids.extend(dirty.get("deleted_memory_ids", []))
            self._cleared_memories.update(dirty.get("cleared_memories", set()))


# Global cache instance
cache = CacheManager()
