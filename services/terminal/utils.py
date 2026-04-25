"""Shared constants/helpers for terminal execution."""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_TIMEOUT_SECONDS = 900
MAX_OUTPUT_CHARS = 24000

BLOCKED_PATTERNS = (
    re.compile(r"(^|\s)rm\s+-rf\s+/(\s|$)"),
    re.compile(r"(^|\s)(shutdown|reboot|poweroff)(\s|$)"),
    re.compile(r"(^|\s)mkfs(\.[^\s]+)?(\s|$)"),
    re.compile(r">\s*/dev/"),
)


def clean_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if any(marker in upper for marker in ("TOKEN", "SECRET", "PASSWORD", "AUTH", "DATABASE_URL", "API_KEY")):
            continue
        env[key] = value
    env.setdefault("PATH", os.environ.get("PATH", ""))
    env.setdefault("HOME", os.environ.get("HOME", "/root"))
    env.setdefault("PYTHONUNBUFFERED", "1")
    # HF Space Ubuntu images use PEP 668 externally-managed Python by default.
    # Enabling this here avoids random pip install failures in terminal skill runs.
    env.setdefault("PIP_BREAK_SYSTEM_PACKAGES", "1")
    env.setdefault("PIP_ROOT_USER_ACTION", "ignore")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    return env


def truncate_output(text: str | None) -> str:
    value = (text or "").strip()
    if len(value) <= MAX_OUTPUT_CHARS:
        return value
    return f"{value[:8000]}\n\n...(truncated)...\n\n{value[-3000:]}"


def resolve_cwd(cwd: str | None, session_cwd: str | None = None) -> Path:
    if not cwd:
        return Path(session_cwd or REPO_ROOT).resolve()
    candidate = Path(cwd)
    if not candidate.is_absolute():
        candidate = Path(session_cwd or REPO_ROOT) / candidate
    return candidate.resolve()


def validate_command(command: str) -> str | None:
    normalized = (command or "").strip()
    if not normalized:
        return "Command cannot be empty."
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(normalized):
            return "Command rejected: contains high-risk system-level destructive operations."
    return None
