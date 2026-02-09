"""Memory management service — CRUD operations with embedding support."""

import logging

from cache import cache
from services.embedding_service import (
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

    Args:
        user_id: User ID
        content: Memory content
        source: 'user' for manual, 'ai' for automatic

    Returns:
        The created memory dict
    """
    content = content.strip()
    embedding = get_embedding(content)

    if embedding:
        logger.info("Memory embedded: '%s...' (source=%s)", content[:50], source)
        existing = cache.get_memories(user_id)
        for i, mem in enumerate(existing):
            if mem.get("embedding"):
                sim = cosine_similarity(embedding, mem["embedding"])
                if sim > MEMORY_DEDUP_THRESHOLD:
                    logger.info(
                        "Dedup: replacing memory (sim=%.3f): '%s' -> '%s'",
                        sim, mem["content"][:40], content[:40],
                    )
                    cache.delete_memory(user_id, i)
                    break
    else:
        logger.info("Memory saved without embedding: '%s...' (source=%s)", content[:50], source)

    return cache.add_memory(user_id, content, source, embedding=embedding)


def delete_memory(user_id: int, index: int) -> bool:
    """Delete a memory by index (1-based for user display, converted to 0-based).

    Args:
        user_id: User ID
        index: 1-based index as shown to user

    Returns:
        True if deleted, False if index invalid
    """
    return cache.delete_memory(user_id, index - 1)


def clear_memories(user_id: int) -> int:
    """Clear all memories for a user.

    Returns:
        Number of memories that were cleared
    """
    count = len(cache.get_memories(user_id))
    cache.clear_memories(user_id)
    return count


def get_memory_count(user_id: int) -> int:
    """Get number of memories for a user."""
    return len(cache.get_memories(user_id))


def format_memories_for_prompt(user_id: int, query: str | None = None) -> str | None:
    """Format memories as a string to include in system prompt.

    When a query is provided and embedding service is available, performs
    vector similarity search to return only relevant memories (top-K above
    threshold). Unembedded legacy memories are always included.

    When no query or embedding service unavailable, returns all memories.

    Args:
        user_id: User ID
        query: Optional user message for semantic search

    Returns:
        Formatted string or None if no memories
    """
    memories = cache.get_memories(user_id)
    if not memories:
        return None

    # Vector search mode
    if query and is_available():
        query_embedding = get_embedding(query)
        if query_embedding:
            scored = []
            unembedded = []

            for mem in memories:
                if mem.get("embedding"):
                    sim = cosine_similarity(query_embedding, mem["embedding"])
                    scored.append((sim, mem))
                else:
                    unembedded.append(mem)

            # Sort by similarity descending, take top-K above threshold
            scored.sort(key=lambda x: x[0], reverse=True)
            relevant = [
                (s, m) for s, m in scored[:MEMORY_TOP_K]
                if s >= MEMORY_SIMILARITY_THRESHOLD
            ]

            selected = [m for _, m in relevant] + unembedded

            # Log search results
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
            for mem in selected:
                lines.append(f"- {mem['content']}")
            return "\n".join(lines)

    # Fallback: return all memories
    logger.info("Memory fallback: returning all %d memories (no vector search)", len(memories))
    lines = ["User memories (use these to personalize responses):"]
    for mem in memories:
        lines.append(f"- {mem['content']}")
    return "\n".join(lines)
