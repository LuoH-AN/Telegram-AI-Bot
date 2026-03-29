"""Minimal terminal execution helpers for skill installation workflows."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .log import record_terminal_command

REPO_ROOT = Path("/root/Telegram-AI-Bot").resolve()
DEFAULT_TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 12000

_BLOCKED_PATTERNS = (
    re.compile(r"(^|\s)rm\s+-rf\s+/(\s|$)"),
    re.compile(r"(^|\s)(shutdown|reboot|poweroff)(\s|$)"),
    re.compile(r"(^|\s)mkfs(\.[^\s]+)?(\s|$)"),
    re.compile(r">\s*/dev/"),
    re.compile(r"(^|\s)(mount|umount|systemctl|service|sudo|su)(\s|$)"),
)


def _clean_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if any(marker in upper for marker in ("TOKEN", "SECRET", "PASSWORD", "AUTH", "DATABASE_URL", "API_KEY")):
            continue
        env[key] = value
    env.setdefault("PATH", os.environ.get("PATH", ""))
    env.setdefault("HOME", os.environ.get("HOME", "/root"))
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _truncate_output(text: str | None) -> str:
    value = (text or "").strip()
    if len(value) <= MAX_OUTPUT_CHARS:
        return value
    head = value[:8000]
    tail = value[-3000:]
    return f"{head}\n\n...(truncated)...\n\n{tail}"


def _resolve_cwd(cwd: str | None) -> Path:
    if not cwd:
        return REPO_ROOT
    candidate = Path(cwd)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate.resolve()


def _validate_command(command: str) -> str | None:
    normalized = (command or "").strip()
    if not normalized:
        return "Command cannot be empty."
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(normalized):
            return "Command rejected: contains high-risk system-level destructive operations."
    return None


def execute_terminal_command(
    user_id: int,
    command: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    error = _validate_command(command)
    resolved_cwd = _resolve_cwd(cwd)
    if error:
        record_terminal_command(
            user_id,
            command=command,
            exit_code=-1,
            cwd=str(resolved_cwd),
            stdout="",
            stderr=error,
            blocked=True,
        )
        return {
            "ok": False,
            "command": command,
            "cwd": str(resolved_cwd),
            "exit_code": -1,
            "stdout": "",
            "stderr": error,
        }

    if not resolved_cwd.exists() or not resolved_cwd.is_dir():
        stderr = f"Working directory does not exist: {resolved_cwd}"
        record_terminal_command(
            user_id,
            command=command,
            exit_code=-1,
            cwd=str(resolved_cwd),
            stdout="",
            stderr=stderr,
        )
        return {
            "ok": False,
            "command": command,
            "cwd": str(resolved_cwd),
            "exit_code": -1,
            "stdout": "",
            "stderr": stderr,
        }

    try:
        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(resolved_cwd),
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
        stdout = _truncate_output(completed.stdout)
        stderr = _truncate_output(completed.stderr)
        record_terminal_command(
            user_id,
            command=command,
            exit_code=completed.returncode,
            cwd=str(resolved_cwd),
            stdout=stdout,
            stderr=stderr,
        )
        return {
            "ok": completed.returncode == 0,
            "command": command,
            "cwd": str(resolved_cwd),
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = _truncate_output(exc.stdout)
        stderr = _truncate_output(exc.stderr)
        timeout_message = f"Command execution timeout (>{int(timeout_seconds)}s)."
        stderr = f"{stderr}\n{timeout_message}".strip() if stderr else timeout_message
        record_terminal_command(
            user_id,
            command=command,
            exit_code=124,
            cwd=str(resolved_cwd),
            stdout=stdout,
            stderr=stderr,
        )
        return {
            "ok": False,
            "command": command,
            "cwd": str(resolved_cwd),
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr,
        }
