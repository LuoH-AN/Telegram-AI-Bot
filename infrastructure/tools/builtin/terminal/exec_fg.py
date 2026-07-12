"""Foreground command execution and working-directory resolution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from infrastructure.tools.core import ToolResult

from .background import _base_env
from .persist import persist_install_command
from .state import REPO_ROOT


def resolve_cwd(cwd: str) -> Path:
    path = Path(cwd).expanduser() if cwd else REPO_ROOT
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def exec_foreground(command: str, cwd_path: Path, timeout: int) -> ToolResult:
    try:
        proc = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(cwd_path),
            env=_base_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ToolResult.error("timeout", f"command timed out after {timeout}s; use background=true for long-running commands")
    parts: list[str] = []
    if proc.stdout:
        parts.append(f"stdout:\n{proc.stdout}")
    if proc.stderr:
        parts.append(f"stderr:\n{proc.stderr}")
    parts.append(f"exit_code: {proc.returncode}")
    if proc.returncode == 0:
        note = persist_install_command(command)
        if note:
            parts.append(note)
    # Failed installers can still leave caches, partial environments and logs.
    # Request a complete snapshot after every terminal mutation opportunity.
    try:
        from entrypoints.launcher.backup import request_snapshot

        request_snapshot()
    except Exception:
        pass
    return ToolResult.text("\n\n".join(parts))
