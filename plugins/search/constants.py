"""Search tool configuration constants."""

from __future__ import annotations

import os

TAVILY_ENDPOINT = os.getenv("TAVILY_ENDPOINT", "https://api.tavily.com/search").strip()
DEFAULT_TIMEOUT = 20
DEFAULT_TOP_K = 8
MAX_TOP_K = 20
DEFAULT_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "basic").strip().lower() or "basic"


def load_api_keys() -> list[str]:
    raw = os.getenv("TAVILY_API_KEYS", "") or os.getenv("TAVILY_API_KEY", "")
    keys: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        key = part.strip()
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    return keys
