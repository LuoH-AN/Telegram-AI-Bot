"""JSON decode helpers used by DB loaders."""

from __future__ import annotations

import json


def parse_json_object(raw_value) -> dict:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_json_list(raw_value) -> list:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []

