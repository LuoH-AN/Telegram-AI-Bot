"""Persist and replay install commands for CLI continuity."""

from __future__ import annotations

import os
import re
from pathlib import Path

INSTALL_PATTERNS = (
    re.compile(r"(^|&&|\|\|)\s*(pip|pip3)\s+install(\s|$)", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*uv\s+tool\s+install(\s|$)", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*npm\s+(i|install)\s+-g(\s|$)", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*pnpm\s+add\s+-g(\s|$)", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*yarn\s+global\s+add(\s|$)", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*apt(-get)?\s+install(\s|$)", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*playwright\s+install(-deps)?(\s|$)", re.IGNORECASE),
)


def _bootstrap_file() -> Path:
    raw = (os.getenv("CLI_BOOTSTRAP_PATH", "/data/telegram_ai_bot_cli_bootstrap.txt") or "").strip()
    return Path(raw or "/data/telegram_ai_bot_cli_bootstrap.txt").expanduser()


def _is_install_command(command: str) -> bool:
    text = (command or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in INSTALL_PATTERNS)


def persist_install_command(command: str) -> str | None:
    text = (command or "").strip()
    if not _is_install_command(text):
        return None
    path = _bootstrap_file()
    try:
        existing: list[str] = []
        if path.exists():
            existing = [line.strip() for line in path.read_text("utf-8", errors="ignore").splitlines()]
        if text in existing:
            return f"persist: install command already tracked in {path}"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            if path.exists() and path.stat().st_size > 0:
                handle.write("\n")
            handle.write(text)
        return f"persist: install command saved to {path}"
    except Exception as exc:
        return f"persist: failed to save install command ({exc})"

