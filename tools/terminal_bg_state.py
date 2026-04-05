"""Shared state for background terminal jobs."""

from __future__ import annotations

import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "runtime" / "terminal" / "bg_logs"
BG_JOBS: dict[int, dict] = {}
BG_LOCK = threading.Lock()


def ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR

