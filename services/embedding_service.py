"""Embedding service — vectorize text via OpenAI-compatible API (NVIDIA / bge-m3)."""

import os
import math
import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

# Configuration from environment
EMBEDDING_API_KEY = os.getenv("NVIDIA_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL", "https://integrate.api.nvidia.com/v1"
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "baai/bge-m3")
MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "10"))
MEMORY_SIMILARITY_THRESHOLD = float(os.getenv("MEMORY_SIMILARITY_THRESHOLD", "0.35"))
MEMORY_DEDUP_THRESHOLD = float(os.getenv("MEMORY_DEDUP_THRESHOLD", "0.85"))

_client = None


def _get_client() -> OpenAI | None:
    """Get or create the embedding client. Returns None if not configured."""
    global _client
    if not EMBEDDING_API_KEY:
        return None
    if _client is None:
        _client = OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL)
        logger.info("Embedding client initialized: model=%s, base_url=%s", EMBEDDING_MODEL, EMBEDDING_BASE_URL)
    return _client


def is_available() -> bool:
    """Check if embedding service is configured."""
    return bool(EMBEDDING_API_KEY)


def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector for a single text string.

    Returns:
        Embedding vector as list of floats, or None on failure / not configured.
    """
    client = _get_client()
    if not client:
        return None
    try:
        response = client.embeddings.create(
            input=[text],
            model=EMBEDDING_MODEL,
            encoding_format="float",
            extra_body={"truncate": "NONE"},
        )
        vec = response.data[0].embedding
        logger.info("Embedded text (%d chars) -> %d-dim vector", len(text), len(vec))
        return vec
    except Exception as e:
        logger.warning("Embedding API call failed: %s", e)
        return None


def get_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """Get embeddings for multiple texts in one API call.

    Returns:
        List of embedding vectors (or None for failed items), same length as input.
    """
    client = _get_client()
    if not client or not texts:
        return [None] * len(texts)
    try:
        response = client.embeddings.create(
            input=texts,
            model=EMBEDDING_MODEL,
            encoding_format="float",
            extra_body={"truncate": "NONE"},
        )
        result: list[list[float] | None] = [None] * len(texts)
        for item in response.data:
            result[item.index] = item.embedding
        logger.info("Batch embedded %d texts", len(texts))
        return result
    except Exception as e:
        logger.warning("Batch embedding API call failed: %s", e)
        return [None] * len(texts)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
