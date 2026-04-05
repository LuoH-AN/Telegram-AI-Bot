"""Shared helpers for settings commands."""


def mask_api_key(key: str) -> str:
    if len(key) > 12:
        return key[:8] + "..." + key[-4:]
    return "***"


def truncate_display(text: str, max_len: int = 80) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text
