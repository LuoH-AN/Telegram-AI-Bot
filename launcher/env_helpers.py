"""Environment parsing helpers for launcher."""

from __future__ import annotations

import os


def _trim(value: str | None) -> str:
    return (value or "").strip()


def get_ports() -> tuple[str, str, str]:
    return (
        os.getenv("TELEGRAM_PORT", "7860"),
        os.getenv("WECHAT_PORT", "7862"),
        os.getenv("ONEBOT_PORT", "7864"),
    )


def apply_env_text() -> None:
    raw = _trim(os.getenv("ENV_TEXT")) or _trim(os.getenv("ENV_CONTENT"))
    if not raw:
        return

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text and "\\n" in text:
        text = text.replace("\\n", "\n")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not (key[0].isalpha() or key[0] == "_"):
            continue
        if any(not (ch.isalnum() or ch == "_") for ch in key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def is_configured_token(token: str | None) -> bool:
    value = _trim(token)
    if not value:
        return False
    return value not in {"your_telegram_bot_token_here", "changeme", "CHANGE_ME"}


def is_wechat_enabled() -> bool:
    return _trim(os.getenv("WECHAT_ENABLED")).lower() in {"1", "true", "yes", "on"}


def is_onebot_enabled() -> bool:
    return _trim(os.getenv("ONEBOT_ENABLED")).lower() in {"1", "true", "yes", "on"}
