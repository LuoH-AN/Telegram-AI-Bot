"""Memory CRUD operations."""

import logging

from cache import cache
from services.embedding import MEMORY_DEDUP_THRESHOLD, cosine_similarity, get_embedding

logger = logging.getLogger(__name__)


def get_memories(user_id: int) -> list[dict]:
    return cache.get_memories(user_id)


def add_memory(user_id: int, content: str, source: str = "user") -> dict:
    content = content.strip()
    embedding = get_embedding(content)
    if embedding:
        existing = cache.get_memories(user_id)
        dup = next(
            (
                (i, mem)
                for i, mem in enumerate(existing)
                if mem.get("embedding") and cosine_similarity(embedding, mem["embedding"]) > MEMORY_DEDUP_THRESHOLD
            ),
            None,
        )
        if dup is not None:
            cache.delete_memory(user_id, dup[0])
    return cache.add_memory(user_id, content, source, embedding=embedding)


def update_memory(user_id: int, index: int, content: str) -> bool:
    zero_index = index - 1
    content = content.strip()
    if not content:
        return False

    memories = cache.get_memories(user_id)
    if not (0 <= zero_index < len(memories)):
        return False

    source = memories[zero_index].get("source", "user")
    embedding = get_embedding(content)
    cache.delete_memory(user_id, zero_index)
    cache.add_memory(user_id, content, source, embedding=embedding)
    if zero_index < len(memories) - 1:
        memories.insert(zero_index, memories.pop())
    return True


def delete_memory(user_id: int, index: int) -> bool:
    return cache.delete_memory(user_id, index - 1)


def clear_memories(user_id: int) -> int:
    count = len(cache.get_memories(user_id))
    cache.clear_memories(user_id)
    return count

