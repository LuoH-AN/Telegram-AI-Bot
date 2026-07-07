"""Nested path helpers for structured config values."""

from __future__ import annotations


def _parts(path: str) -> list[str]:
    return [part for part in str(path or "").split(".") if part]


def get_path(data: dict, path: str):
    current = data
    for part in _parts(path):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def set_path(data: dict, path: str, value) -> None:
    parts = _parts(path)
    if not parts:
        raise ValueError("key path is required")
    current = data
    for part in parts[:-1]:
        next_value = current.get(part)
        if next_value is None:
            current[part] = {}
            next_value = current[part]
        if not isinstance(next_value, dict):
            raise ValueError(f"Cannot set nested key through non-object: {path}")
        current = next_value
    current[parts[-1]] = value


def delete_path(data: dict, path: str) -> bool:
    parts = _parts(path)
    if not parts:
        return False
    current = data
    for part in parts[:-1]:
        current = current.get(part)
        if not isinstance(current, dict):
            return False
    if not isinstance(current, dict) or parts[-1] not in current:
        return False
    current.pop(parts[-1])
    return True
