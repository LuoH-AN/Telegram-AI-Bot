"""Shared state for background terminal jobs."""

from __future__ import annotations

import threading
from pathlib import Path

def _find_repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "main.py").is_file() and (parent / "infrastructure").is_dir():
            return parent
    return path.parents[3]


REPO_ROOT = _find_repo_root()
LOG_DIR = REPO_ROOT / "runtime" / "terminal" / "bg_logs"
BG_JOBS: dict[int, dict] = {}
BG_LOCK = threading.Lock()


def ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR
