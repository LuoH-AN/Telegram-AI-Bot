"""Small helper utilities for SoSearch tool."""

from __future__ import annotations

import json


def as_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def as_port(value, *, default: int) -> int:
    return as_int(value, default=default, minimum=1024, maximum=65535)


def as_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)

