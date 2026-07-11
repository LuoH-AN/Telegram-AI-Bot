"""Helper functions for infrastructure.config settings."""

from __future__ import annotations

import hashlib
import os
import re

from .telegram_ux import DEFAULT_TELEGRAM_BUSY_MODE, DEFAULT_TELEGRAM_TOOL_PROGRESS

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def apply_env_text() -> None:
    raw = os.getenv("ENV_TEXT", "") or os.getenv("ENV_CONTENT", "")
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
        if not _ENV_NAME_RE.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def normalize_reasoning_effort(value: str | None, allowed_values: set[str]) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed_values else ""


def normalize_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on", "y"}:
        return True
    if raw in {"0", "false", "no", "off", "n"}:
        return False
    return default


def build_default_jwt_secret() -> str:
    seed = (
        os.getenv("JWT_SECRET_SEED", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or "gemen-local-dev-secret"
    )
    return hashlib.sha256(f"gemen:{seed}".encode("utf-8")).hexdigest()


def build_default_settings(
    *,
    default_reasoning_effort: str,
    default_show_thinking: bool,
) -> dict:
    return {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
        "reasoning_effort": default_reasoning_effort,
        "show_thinking": default_show_thinking,
        "stream_mode": "",
        "busy_mode": DEFAULT_TELEGRAM_BUSY_MODE,
        "tool_progress": DEFAULT_TELEGRAM_TOOL_PROGRESS,
        "token_limit": 0,
        "current_persona": "default",
        "api_presets": {},
        "title_model": "",
        "cron_model": "",
        "global_prompt": "",
        "timezone": os.getenv("DEFAULT_TIMEZONE", "Asia/Shanghai"),
        "terminal_approvals": [],
    }
