"""Memory cache mixin."""

from __future__ import annotations


class MemoriesMixin:
    def get_memories(self, user_id: int) -> list[dict]:
        self._memories_cache.setdefault(user_id, [])
        return self._memories_cache[user_id]

    def add_memory(self, user_id: int, content: str, source: str = "user", embedding: list[float] | None = None) -> dict:
        self._memories_cache.setdefault(user_id, [])
        memory = {"id": None, "user_id": user_id, "content": content, "source": source, "embedding": embedding}
        self._memories_cache[user_id].append(memory)
        with self._lock:
            self._new_memories.append(memory)
        return memory

    def delete_memory(self, user_id: int, memory_index: int) -> bool:
        memories = self.get_memories(user_id)
        if 0 <= memory_index < len(memories):
            removed = memories.pop(memory_index)
            if removed.get("id") is not None:
                with self._lock:
                    self._deleted_memory_ids.append(removed["id"])
            return True
        return False

    def clear_memories(self, user_id: int) -> None:
        self._memories_cache[user_id] = []
        with self._lock:
            self._cleared_memories.add(user_id)

    def set_memories(self, user_id: int, memories: list[dict]) -> None:
        self._memories_cache[user_id] = memories
