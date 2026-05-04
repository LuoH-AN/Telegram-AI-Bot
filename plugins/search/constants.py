"""Search runtime constants and paths."""

from __future__ import annotations

import threading

from ..terminal.state import REPO_ROOT

DEFAULT_PORT = 18080
DEFAULT_TIMEOUT = 20
DEFAULT_REPO_URL = "https://github.com/netlops/SoSearch.git"
STATE_LOCK = threading.RLock()

BASE_DIR = REPO_ROOT / "runtime" / "search"
REPO_DIR = BASE_DIR / "SoSearch"
BIN_DIR = BASE_DIR / "bin"
STATE_FILE = BASE_DIR / "state.json"
LOG_DIR = BASE_DIR / "logs"

