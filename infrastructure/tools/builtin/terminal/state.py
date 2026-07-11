"""Shared state for terminal background jobs."""

from __future__ import annotations

import os
from pathlib import Path


def _find_repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "main.py").is_file() and (parent / "infrastructure").is_dir():
            return parent
    return path.parents[4]


REPO_ROOT = _find_repo_root()
_configured_dir = (os.getenv("TERMINAL_STATE_DIR") or "").strip()
if _configured_dir:
    TERMINAL_DIR = Path(_configured_dir).expanduser().resolve()
elif Path("/data").is_dir():
    TERMINAL_DIR = Path("/data/telegram_ai_bot/terminal")
else:
    TERMINAL_DIR = REPO_ROOT / "runtime" / "terminal"
LOG_DIR = TERMINAL_DIR / "logs"
CONTROL_DIR = TERMINAL_DIR / "control"


def ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def ensure_control_dir() -> Path:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    return CONTROL_DIR
