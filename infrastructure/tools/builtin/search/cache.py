"""Small in-memory TTL cache for Exa search results."""

from __future__ import annotations

import copy
import os
import threading
import time
from collections import OrderedDict


class SearchCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    @property
    def ttl(self) -> int:
        return max(0, int(os.getenv("EXA_CACHE_TTL", "300")))

    @property
    def max_entries(self) -> int:
        return max(1, int(os.getenv("EXA_CACHE_MAX_ENTRIES", "256")))

    def get(self, key: str) -> dict | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self._misses += 1
                return None
            created_at, value = item
            if self.ttl <= 0 or time.monotonic() - created_at > self.ttl:
                self._items.pop(key, None)
                self._misses += 1
                return None
            self._items.move_to_end(key)
            self._hits += 1
            return copy.deepcopy(value)

    def set(self, key: str, value: dict) -> None:
        if self.ttl <= 0:
            return
        with self._lock:
            self._items[key] = (time.monotonic(), copy.deepcopy(value))
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._hits = 0
            self._misses = 0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "enabled": self.ttl > 0,
                "ttl_seconds": self.ttl,
                "size": len(self._items),
                "max_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
            }


SEARCH_CACHE = SearchCache()
