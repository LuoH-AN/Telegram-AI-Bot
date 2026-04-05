"""Memory formatting for prompt assembly."""

import logging

from cache import cache
from services.embedding import MEMORY_SIMILARITY_THRESHOLD, MEMORY_TOP_K, get_embedding, is_available

from .scoring import score_memories

logger = logging.getLogger(__name__)


def _format_lines(title: str, memories: list[dict]) -> str:
    lines = [title]
    lines.extend(f"- {memory['content']}" for memory in memories)
    return "\n".join(lines)


def format_memories_for_prompt(user_id: int, query: str | None = None) -> str | None:
    memories = cache.get_memories(user_id)
    if not memories:
        return None

    if query and is_available():
        query_embedding = get_embedding(query)
        if query_embedding:
            scored, unembedded = score_memories(memories, query_embedding)
            relevant = [(score, memory) for score, memory in scored[:MEMORY_TOP_K] if score >= MEMORY_SIMILARITY_THRESHOLD]
            selected = [memory for _, memory in relevant] + unembedded
            if not selected:
                return None
            return _format_lines("User memories (relevant to current conversation):", selected)

    return _format_lines("User memories (use these to personalize responses):", memories)

