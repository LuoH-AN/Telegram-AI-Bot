"""Builtin command handling for terminal sessions."""

from __future__ import annotations

import os
import re
import shlex

from .state import TerminalSessionState

from .utils import REPO_ROOT, resolve_cwd


def apply_shell_builtin(command: str, session: TerminalSessionState) -> dict | None:
    normalized = (command or "").strip()
    if not normalized:
        return {"ok": False, "exit_code": -1, "stdout": "", "stderr": "Command cannot be empty."}
    if normalized == "pwd":
        return {"ok": True, "exit_code": 0, "stdout": session.cwd, "stderr": ""}
    if normalized == "env":
        rendered = "\n".join(f"{key}={value}" for key, value in sorted(session.env.items()))
        return {"ok": True, "exit_code": 0, "stdout": rendered, "stderr": ""}

    if normalized.startswith("cd"):
        try:
            parts = shlex.split(normalized)
        except ValueError as exc:
            return {"ok": False, "exit_code": 2, "stdout": "", "stderr": str(exc)}
        target = parts[1] if len(parts) > 1 else os.getenv("HOME") or str(REPO_ROOT)
        if target == "-":
            target = session.previous_cwd or session.cwd
        resolved = resolve_cwd(target, session.cwd)
        if not resolved.exists() or not resolved.is_dir():
            return {"ok": False, "exit_code": 1, "stdout": "", "stderr": f"Directory does not exist: {resolved}"}
        session.previous_cwd = session.cwd
        session.cwd = str(resolved)
        return {"ok": True, "exit_code": 0, "stdout": session.cwd, "stderr": ""}

    if normalized.startswith("export "):
        assignment = normalized[len("export "):].strip()
        if "=" not in assignment:
            return {"ok": False, "exit_code": 2, "stdout": "", "stderr": "Usage: export KEY=VALUE"}
        key, value = assignment.split("=", 1)
        key = key.strip()
        if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            return {"ok": False, "exit_code": 2, "stdout": "", "stderr": f"Invalid environment variable name: {key!r}"}
        session.env[key] = value
        return {"ok": True, "exit_code": 0, "stdout": f"{key}={value}", "stderr": ""}

    if normalized.startswith("unset "):
        key = normalized[len("unset "):].strip()
        session.env.pop(key, None)
        return {"ok": True, "exit_code": 0, "stdout": key, "stderr": ""}

    if normalized in {"reset", "reset-session"}:
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": ""}
    return None
