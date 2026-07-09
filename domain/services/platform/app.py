"""Shared runtime utilities for platform domain.services."""

from __future__ import annotations

from infrastructure.ai import get_ai_client
from infrastructure.config import VALID_REASONING_EFFORTS, normalize_reasoning_effort


def mask_key(api_key: str) -> str:
    if not api_key:
        return "(empty)"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"


def normalize_stream_mode(mode: str | None) -> str:
    current = (mode or "").strip().lower()
    return current if current in {"default", "time", "chars", "off"} else "default"


def fetch_models_for_user(user_id: int) -> list[str]:
    try:
        return get_ai_client(user_id).list_models()
    except Exception:
        return []
