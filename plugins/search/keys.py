"""Tavily API key pool with round-robin and per-key cooldown."""

from __future__ import annotations

import threading
import time

from .constants import load_api_keys

COOLDOWN_RATE_LIMIT = 60.0
COOLDOWN_AUTH_FAIL = 3600.0
COOLDOWN_NETWORK = 10.0


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:6]}…{key[-4:]}"


class KeyPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._keys: list[str] = load_api_keys()
        self._cursor = 0
        self._cooldown: dict[str, float] = {}
        self._last_error: dict[str, str] = {}

    def reload(self) -> None:
        with self._lock:
            self._keys = load_api_keys()
            self._cursor = 0
            self._cooldown.clear()
            self._last_error.clear()

    def has_keys(self) -> bool:
        with self._lock:
            return bool(self._keys)

    def acquire(self) -> str | None:
        with self._lock:
            if not self._keys:
                return None
            now = time.time()
            n = len(self._keys)
            for _ in range(n):
                idx = self._cursor % n
                self._cursor = (self._cursor + 1) % n
                key = self._keys[idx]
                if self._cooldown.get(key, 0.0) <= now:
                    return key
            return None

    def report_failure(self, key: str, kind: str, message: str = "") -> None:
        cooldown = {
            "rate_limit": COOLDOWN_RATE_LIMIT,
            "auth": COOLDOWN_AUTH_FAIL,
            "network": COOLDOWN_NETWORK,
        }.get(kind, COOLDOWN_NETWORK)
        with self._lock:
            self._cooldown[key] = time.time() + cooldown
            self._last_error[key] = f"{kind}: {message}".strip(": ")

    def report_success(self, key: str) -> None:
        with self._lock:
            self._cooldown.pop(key, None)
            self._last_error.pop(key, None)

    def snapshot(self) -> dict:
        with self._lock:
            now = time.time()
            keys_info = []
            for k in self._keys:
                cd = self._cooldown.get(k, 0.0)
                keys_info.append({
                    "key": _mask(k),
                    "available": cd <= now,
                    "cooldown_remaining": max(0, int(cd - now)),
                    "last_error": self._last_error.get(k, ""),
                })
            return {
                "configured": len(self._keys),
                "available": sum(1 for it in keys_info if it["available"]),
                "keys": keys_info,
            }


KEY_POOL = KeyPool()
