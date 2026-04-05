"""Terminal execution helpers with persistent session state."""

from __future__ import annotations

import os
import re
import subprocess
import shlex
from pathlib import Path

from .log import record_terminal_command
from .terminal_session import (
    TerminalSessionState,
    get_terminal_session,
    reset_terminal_session,
    save_terminal_session,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT_SECONDS = 900
MAX_OUTPUT_CHARS = 24000

_BLOCKED_PATTERNS = (
    re.compile(r"(^|\s)rm\s+-rf\s+/(\s|$)"),
    re.compile(r"(^|\s)(shutdown|reboot|poweroff)(\s|$)"),
    re.compile(r"(^|\s)mkfs(\.[^\s]+)?(\s|$)"),
    re.compile(r">\s*/dev/"),
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


def _resolve_cwd(cwd: str | None, session_cwd: str | None = None) -> Path:
    if not cwd:
        return Path(session_cwd or REPO_ROOT).resolve()
    candidate = Path(cwd)
    if not candidate.is_absolute():
        candidate = Path(session_cwd or REPO_ROOT) / candidate
    return candidate.resolve()


def _validate_command(command: str) -> str | None:
    normalized = (command or "").strip()
    if not normalized:
        return "Command cannot be empty."
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(normalized):
            return "Command rejected: contains high-risk system-level destructive operations."
    return None


def _apply_shell_builtin(command: str, session: TerminalSessionState) -> dict | None:
    normalized = (command or "").strip()
    if not normalized:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "Command cannot be empty.",
        }

    if normalized == "pwd":
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": session.cwd,
            "stderr": "",
        }

    if normalized == "env":
        rendered = "\n".join(f"{key}={value}" for key, value in sorted(session.env.items()))
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": rendered,
            "stderr": "",
        }

    if normalized.startswith("cd"):
        try:
            parts = shlex.split(normalized)
        except ValueError as exc:
            return {"ok": False, "exit_code": 2, "stdout": "", "stderr": str(exc)}
        target = parts[1] if len(parts) > 1 else os.getenv("HOME") or str(REPO_ROOT)
        if target == "-":
            target = session.previous_cwd or session.cwd
        resolved = _resolve_cwd(target, session.cwd)
        if not resolved.exists() or not resolved.is_dir():
            return {
                "ok": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Directory does not exist: {resolved}",
            }
        session.previous_cwd = session.cwd
        session.cwd = str(resolved)
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": session.cwd,
            "stderr": "",
        }

    if normalized.startswith("export "):
        assignment = normalized[len("export "):].strip()
        if "=" not in assignment:
            return {
                "ok": False,
                "exit_code": 2,
                "stdout": "",
                "stderr": "Usage: export KEY=VALUE",
            }
        key, value = assignment.split("=", 1)
        key = key.strip()
        if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            return {
                "ok": False,
                "exit_code": 2,
                "stdout": "",
                "stderr": f"Invalid environment variable name: {key!r}",
            }
        session.env[key] = value
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": f"{key}={value}",
            "stderr": "",
        }

    if normalized.startswith("unset "):
        key = normalized[len("unset "):].strip()
        session.env.pop(key, None)
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": key,
            "stderr": "",
        }

    if normalized in {"reset", "reset-session"}:
        return {
            "ok": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
        }

    return None


def execute_terminal_command(
    user_id: int,
    command: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    session_name: str = "default",
) -> dict:
    session = get_terminal_session(user_id, session_name=session_name)
    builtin = _apply_shell_builtin(command, session)
    if builtin is not None:
        if (command or "").strip() in {"reset", "reset-session"}:
            session = reset_terminal_session(user_id, session_name=session_name)
            builtin["stdout"] = session.cwd
        session.last_command = command
        session.last_exit_code = builtin["exit_code"]
        save_terminal_session(user_id, session, session_name=session_name)
        record_terminal_command(
            user_id,
            command=command,
            exit_code=builtin["exit_code"],
            cwd=session.cwd,
            stdout=_truncate_output(builtin["stdout"]),
            stderr=_truncate_output(builtin["stderr"]),
        )
        return {
            "ok": builtin["ok"],
            "command": command,
            "cwd": session.cwd,
            "session_name": session_name,
            "exit_code": builtin["exit_code"],
            "stdout": _truncate_output(builtin["stdout"]),
            "stderr": _truncate_output(builtin["stderr"]),
            "env": dict(session.env),
            "session": {
                "cwd": session.cwd,
                "previous_cwd": session.previous_cwd,
                "last_command": session.last_command,
                "last_exit_code": session.last_exit_code,
            },
        }

    error = _validate_command(command)
    resolved_cwd = _resolve_cwd(cwd, session.cwd)
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
            "session_name": session_name,
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
            "session_name": session_name,
            "exit_code": -1,
            "stdout": "",
            "stderr": stderr,
        }

    try:
        env = _clean_env()
        env.update(session.env)
        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(resolved_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
        stdout = _truncate_output(completed.stdout)
        stderr = _truncate_output(completed.stderr)
        session.previous_cwd = session.cwd
        session.cwd = str(resolved_cwd)
        session.last_command = command
        session.last_exit_code = completed.returncode
        save_terminal_session(user_id, session, session_name=session_name)
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
            "session_name": session_name,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "env": dict(session.env),
            "session": {
                "cwd": session.cwd,
                "previous_cwd": session.previous_cwd,
                "last_command": session.last_command,
                "last_exit_code": session.last_exit_code,
            },
        }
    except subprocess.TimeoutExpired as exc:
        stdout = _truncate_output(exc.stdout)
        stderr = _truncate_output(exc.stderr)
        timeout_message = f"Command execution timeout (>{int(timeout_seconds)}s)."
        stderr = f"{stderr}\n{timeout_message}".strip() if stderr else timeout_message
        session.previous_cwd = session.cwd
        session.cwd = str(resolved_cwd)
        session.last_command = command
        session.last_exit_code = 124
        save_terminal_session(user_id, session, session_name=session_name)
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
            "session_name": session_name,
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr,
            "env": dict(session.env),
            "session": {
                "cwd": session.cwd,
                "previous_cwd": session.previous_cwd,
                "last_command": session.last_command,
                "last_exit_code": session.last_exit_code,
            },
        }
