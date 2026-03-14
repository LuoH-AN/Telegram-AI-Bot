"""HF backup gate shared by shell and browser snapshots."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass


def _get_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, str(default)) or str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


_THRESHOLD = _get_int_env("HF_BACKUP_TRIGGER_COUNT", 15)


@dataclass
class _UserBackupState:
    shell_count: int = 0
    browser_count: int = 0
    shell_ticket: int = 0
    browser_ticket: int = 0


_LOCK = threading.Lock()
_STATE: dict[int, _UserBackupState] = {}


def _should_backup(user_id: int, source: str) -> bool:
    threshold = _THRESHOLD
    if threshold <= 0:
        return True

    with _LOCK:
        state = _STATE.setdefault(user_id, _UserBackupState())

        if source == "shell":
            if state.shell_ticket > 0:
                state.shell_ticket -= 1
                return True
            state.shell_count += 1
        elif source == "browser":
            if state.browser_ticket > 0:
                state.browser_ticket -= 1
                return True
            state.browser_count += 1
        else:
            raise ValueError(f"unknown backup source: {source}")

        if state.shell_count >= threshold and state.browser_count >= threshold:
            state.shell_ticket += 1
            state.browser_ticket += 1
            state.shell_count = 0
            state.browser_count = 0
            if source == "shell":
                state.shell_ticket -= 1
            else:
                state.browser_ticket -= 1
            return True

        return False


def should_backup_shell(user_id: int) -> bool:
    return _should_backup(user_id, "shell")


def should_backup_browser(user_id: int) -> bool:
    return _should_backup(user_id, "browser")
