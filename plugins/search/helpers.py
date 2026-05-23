"""Small helper utilities for search tool."""

from __future__ import annotations

import json


def as_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def as_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)

