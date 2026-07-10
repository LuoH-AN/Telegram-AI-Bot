"""Exa API key pool: round-robin with per-key cooldown."""

from __future__ import annotations

import os
import threading
import time


SEARCH_TYPES = {"instant", "fast", "auto", "deep-lite", "deep", "deep-reasoning"}


def exa_endpoint() -> str:
    return os.getenv("EXA_ENDPOINT", "https://api.exa.ai/search").strip()


def default_search_type() -> str:
    value = os.getenv("EXA_SEARCH_TYPE", "auto").strip().lower() or "auto"
    return value if value in SEARCH_TYPES else "auto"


COOLDOWN_RATE_LIMIT = 60.0
COOLDOWN_AUTH_FAIL = 3600.0
COOLDOWN_NETWORK = 10.0


def load_api_keys() -> list[str]:
    raw = os.getenv("EXA_API_KEYS", "") or os.getenv("EXA_API_KEY", "")
    keys: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        key = part.strip()
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    return keys


def _mask(key: str) -> str:
    return f"{key[:6]}…{key[-4:]}" if len(key) > 8 else "***"


class KeyPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._keys = load_api_keys()
        self._cursor = 0
        self._cooldown: dict[str, float] = {}
        self._last_error: dict[str, str] = {}

    def _reload_if_changed(self) -> None:
        current = load_api_keys()
        if current == self._keys:
            return
        self._keys = current
        self._cursor = 0
        self._cooldown = {key: value for key, value in self._cooldown.items() if key in current}
        self._last_error = {key: value for key, value in self._last_error.items() if key in current}

    def reload(self) -> None:
        with self._lock:
            self._keys = load_api_keys()
            self._cursor = 0
            self._cooldown.clear()
            self._last_error.clear()

    def acquire(self) -> str | None:
        with self._lock:
            self._reload_if_changed()
            if not self._keys:
                return None
            now = time.time()
            count = len(self._keys)
            for _ in range(count):
                idx = self._cursor % count
                self._cursor = (self._cursor + 1) % count
                key = self._keys[idx]
                if self._cooldown.get(key, 0.0) <= now:
                    return key
            return None

    def report_failure(self, key: str, kind: str, message: str = "") -> None:
        cooldown = {"rate_limit": COOLDOWN_RATE_LIMIT, "auth": COOLDOWN_AUTH_FAIL}.get(kind, COOLDOWN_NETWORK)
        with self._lock:
            self._cooldown[key] = time.time() + cooldown
            self._last_error[key] = f"{kind}: {message}".strip(": ")

    def report_success(self, key: str) -> None:
        with self._lock:
            self._cooldown.pop(key, None)
            self._last_error.pop(key, None)

    def snapshot(self) -> dict:
        with self._lock:
            self._reload_if_changed()
            now = time.time()
            info = []
            for key in self._keys:
                cooldown = self._cooldown.get(key, 0.0)
                info.append({"key": _mask(key), "available": cooldown <= now, "cooldown_remaining": max(0, int(cooldown - now)), "last_error": self._last_error.get(key, "")})
            return {"configured": len(self._keys), "available": sum(1 for it in info if it["available"]), "keys": info}


KEY_POOL = KeyPool()
