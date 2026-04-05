"""Memory scoring helpers."""

from services.embedding import cosine_similarity


def score_memories(
    memories: list[dict],
    query_embedding: list[float],
) -> tuple[list[tuple[float, dict]], list[dict]]:
    scored: list[tuple[float, dict]] = []
    unembedded: list[dict] = []
    for memory in memories:
        if memory.get("embedding"):
            scored.append((cosine_similarity(query_embedding, memory["embedding"]), memory))
        else:
            unembedded.append(memory)
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored, unembedded

