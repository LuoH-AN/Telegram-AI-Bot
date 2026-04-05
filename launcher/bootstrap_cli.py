"""Replay persisted CLI install commands at startup."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = (os.getenv("CLI_BOOTSTRAP_ENABLED", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on", "y"}


def _bootstrap_file() -> Path:
    raw = (os.getenv("CLI_BOOTSTRAP_PATH", "/data/telegram_ai_bot_cli_bootstrap.txt") or "").strip()
    return Path(raw or "/data/telegram_ai_bot_cli_bootstrap.txt").expanduser()


def run_cli_bootstrap(*, root_dir: Path) -> None:
    if not _enabled():
        return
    path = _bootstrap_file()
    if not path.exists():
        return
    timeout = int((os.getenv("CLI_BOOTSTRAP_TIMEOUT_SECONDS", "1800") or "1800").strip() or "1800")
    commands = [line.strip() for line in path.read_text("utf-8", errors="ignore").splitlines() if line.strip() and not line.strip().startswith("#")]
    if not commands:
        return
    logger.info("CLI bootstrap: running %d command(s) from %s", len(commands), path)
    for idx, command in enumerate(commands, start=1):
        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                timeout=max(1, timeout),
            )
        except Exception as exc:
            logger.warning("CLI bootstrap [%d/%d] failed: %s", idx, len(commands), exc)
            continue
        if completed.returncode == 0:
            logger.info("CLI bootstrap [%d/%d] ok: %s", idx, len(commands), command[:120])
        else:
            stderr = (completed.stderr or completed.stdout or "").strip()
            logger.warning("CLI bootstrap [%d/%d] exit=%d: %s | %s", idx, len(commands), completed.returncode, command[:120], stderr[:240])

