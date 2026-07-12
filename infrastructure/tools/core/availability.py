"""Tool availability gating: env requirements and runtime checks with TTL cache."""

from __future__ import annotations

import os
import time

_CACHE: dict[tuple[str, int], tuple[bool, float]] = {}
_TTL_SECONDS = 30.0


def env_satisfied(required: tuple[str, ...]) -> bool:
    return all((os.getenv(name) or "").strip() for name in required)


def check_available(entry) -> bool:
    if not env_satisfied(getattr(entry, "requires_env", ())):
        return False
    check_fn = getattr(entry, "check_fn", None)
    if check_fn is None:
        return True
    key = (entry.name, id(check_fn))
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and (now - hit[1]) < _TTL_SECONDS:
        return hit[0]
    try:
        ok = bool(check_fn())
    except Exception:
        ok = False
    _CACHE[key] = (ok, now)
    return ok
