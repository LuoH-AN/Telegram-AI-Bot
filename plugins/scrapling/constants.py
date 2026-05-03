"""Shared constants and paths for scrapling tool integration."""

from __future__ import annotations

from pathlib import Path

from ..terminal.state import REPO_ROOT

RUNTIME_DIR = REPO_ROOT / "runtime" / "scrapling"
COOKIE_VAULT_FILE = RUNTIME_DIR / "cookie_vault.json"
INSTALL_LOG_FILE = RUNTIME_DIR / "install.log"

DEFAULT_TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 6000

ALLOWED_MODES = {"auto", "basic", "stealth", "dynamic"}

