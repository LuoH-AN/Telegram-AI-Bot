"""Shared helper functions for OpenAI client logging and validation."""

from __future__ import annotations


def _shorten_text(text: str, limit: int = 120) -> str:
    normalized = (text or "").replace("\n", "\\n")
    return normalized if len(normalized) <= limit else normalized[:limit] + "..."


def _preview_content(content: object, *, limit: int = 120) -> str:
    if content is None:
        return "(none)"
    if isinstance(content, str):
        stripped = content.strip()
        return "(empty)" if not stripped else _shorten_text(stripped, limit)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content[:3]:
            if isinstance(item, dict):
                item_type = str(item.get("type", "unknown"))
                if item_type == "text":
                    text_part = str(item.get("text", "")).strip()
                    parts.append(f"text:{_shorten_text(text_part, 60) if text_part else '(empty)'}")
                else:
                    parts.append(item_type)
            else:
                parts.append(type(item).__name__)
        suffix = ", ..." if len(content) > 3 else ""
        return "[" + ", ".join(parts) + suffix + "]"
    return _shorten_text(str(content), limit)


def _role_summary(messages: list[dict]) -> str:
    counts: dict[str, int] = {}
    for message in messages:
        role = str(message.get("role", "unknown")) if isinstance(message, dict) else "unknown"
        counts[role] = counts.get(role, 0) + 1
    return ",".join(f"{role}:{counts[role]}" for role in sorted(counts)) if counts else "-"


def _find_last_user_preview(messages: list[dict]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return _preview_content(message.get("content"))
    return "(none)"


def _text_size(value: object) -> int:
    if value is None:
        return 0
    return len(value) if isinstance(value, str) else len(str(value))


def _is_reasoning_param_error(error_text: str) -> bool:
    normalized = (error_text or "").lower()
    if "reasoning_effort" not in normalized:
        return False
    markers = (
        "unsupported",
        "unknown",
        "unrecognized",
        "not allowed",
        "not supported",
        "extra inputs are not permitted",
        "unexpected keyword argument",
        "invalid parameter",
    )
    return any(marker in normalized for marker in markers)
