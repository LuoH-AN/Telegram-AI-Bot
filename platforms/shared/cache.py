"""Small TTL caches used for dedupe/echo suppression."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict


class RecentKeyCache:
    """Thread-safe TTL cache for tracking recently seen keys.

    Used for message deduplication and echo suppression across platforms.
    """

    def __init__(self, *, ttl_seconds: int, max_items: int):
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._lock = threading.RLock()
        self._items: OrderedDict[str, float] = OrderedDict()

    def _prune(self, now: float) -> None:
        expired = [key for key, ts in self._items.items() if now - ts > self._ttl_seconds]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)

    def seen(self, key: str | None) -> bool:
        """Check if key was seen recently, updating its position."""
        if not key:
            return False
        now = time.time()
        with self._lock:
            self._prune(now)
            if key in self._items:
                self._items.move_to_end(key)
                return True
            return False

    def remember(self, key: str | None) -> None:
        """Mark a key as seen."""
        if key:
            now = time.time()
            with self._lock:
                self._prune(now)
                self._items[key] = now
                self._items.move_to_end(key)

    def remember_once(self, key: str | None) -> bool:
        """Mark key as seen, return True if already seen."""
        if not key:
            return False
        now = time.time()
        with self._lock:
            self._prune(now)
            if key in self._items:
                self._items.move_to_end(key)
                return True
            self._items[key] = now
            self._items.move_to_end(key)
            return False


class NoopPump:
    """No-op pump for platforms that don't need typing indicators."""

    def force_stop(self) -> None:
        return None
