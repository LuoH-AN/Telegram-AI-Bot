"""Memory management service — CRUD operations with embedding support."""

import logging

from cache import cache
from services.embedding import (
    get_embedding,
    cosine_similarity,
    is_available,
    MEMORY_TOP_K,
    MEMORY_SIMILARITY_THRESHOLD,
    MEMORY_DEDUP_THRESHOLD,
)

logger = logging.getLogger(__name__)


def get_memories(user_id: int) -> list[dict]:
    """Get all memories for a user."""
    return cache.get_memories(user_id)


def add_memory(user_id: int, content: str, source: str = "user") -> dict:
    """Add a memory for a user, with embedding and deduplication.

    Flow:
        1. Compute embedding for the content (if service available)
        2. Check existing memories for semantic duplicates (similarity > threshold)
        3. If duplicate found, remove old and add new (update semantics)
        4. Otherwise add as new memory
    """
    content = content.strip()
    embedding = get_embedding(content)

    if embedding:
        logger.info("Memory embedded: '%s...' (source=%s)", content[:50], source)
        existing = cache.get_memories(user_id)
        dup = next(
            (
                (i, mem) for i, mem in enumerate(existing)
                if mem.get("embedding")
                and cosine_similarity(embedding, mem["embedding"]) > MEMORY_DEDUP_THRESHOLD
            ),
            None,
        )
        if dup is not None:
            i, mem = dup
            sim = cosine_similarity(embedding, mem["embedding"])
            logger.info(
                "Dedup: replacing memory (sim=%.3f): '%s' -> '%s'",
                sim, mem["content"][:40], content[:40],
            )
            cache.delete_memory(user_id, i)
    else:
        logger.info("Memory saved without embedding: '%s...' (source=%s)", content[:50], source)

    return cache.add_memory(user_id, content, source, embedding=embedding)


def update_memory(user_id: int, index: int, content: str) -> bool:
    """Update a memory by index (1-based), preserving list order."""
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

    # Keep edited memory at its original position instead of moving to end.
    if zero_index < len(memories) - 1:
        memories.insert(zero_index, memories.pop())

    return True


def delete_memory(user_id: int, index: int) -> bool:
    """Delete a memory by index (1-based for user display, converted to 0-based)."""
    return cache.delete_memory(user_id, index - 1)


def clear_memories(user_id: int) -> int:
    """Clear all memories for a user. Returns number of memories cleared."""
    count = len(cache.get_memories(user_id))
    cache.clear_memories(user_id)
    return count


def _score_memories(
    memories: list[dict], query_embedding: list[float]
) -> tuple[list[tuple[float, dict]], list[dict]]:
    """Score memories by similarity to query embedding.

    Returns (scored_pairs, unembedded_memories).
    """
    scored = []
    unembedded = []
    for mem in memories:
        if mem.get("embedding"):
            scored.append((cosine_similarity(query_embedding, mem["embedding"]), mem))
        else:
            unembedded.append(mem)
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored, unembedded


def format_memories_for_prompt(user_id: int, query: str | None = None) -> str | None:
    """Format memories as a string to include in system prompt.

    When a query is provided and embedding service is available, performs
    vector similarity search to return only relevant memories (top-K above
    threshold). Unembedded legacy memories are always included.

    When no query or embedding service unavailable, returns all memories.
    """
    memories = cache.get_memories(user_id)
    if not memories:
        return None

    # Vector search mode
    if query and is_available():
        query_embedding = get_embedding(query)
        if query_embedding:
            scored, unembedded = _score_memories(memories, query_embedding)

            relevant = [
                (s, m) for s, m in scored[:MEMORY_TOP_K]
                if s >= MEMORY_SIMILARITY_THRESHOLD
            ]
            selected = [m for _, m in relevant] + unembedded

            if scored:
                top_scores = ", ".join(f"{s:.3f}" for s, _ in scored[:5])
                logger.info(
                    "Memory vector search: query='%s...' | %d memories scored, "
                    "%d above threshold (%.2f), %d unembedded | top scores: [%s]",
                    query[:40], len(scored), len(relevant),
                    MEMORY_SIMILARITY_THRESHOLD, len(unembedded), top_scores,
                )
            else:
                logger.info(
                    "Memory vector search: query='%s...' | 0 embedded, %d unembedded (fallback)",
                    query[:40], len(unembedded),
                )

            if not selected:
                logger.info("Memory vector search: no relevant memories found")
                return None

            lines = ["User memories (relevant to current conversation):"]
            lines.extend(f"- {mem['content']}" for mem in selected)
            return "\n".join(lines)

    # Fallback: return all memories
    logger.info("Memory fallback: returning all %d memories (no vector search)", len(memories))
    lines = ["User memories (use these to personalize responses):"]
    lines.extend(f"- {mem['content']}" for mem in memories)
    return "\n".join(lines)
