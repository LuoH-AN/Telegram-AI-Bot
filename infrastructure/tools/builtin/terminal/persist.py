"""Persist and replay install commands for CLI continuity across restarts."""

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
    re.compile(r"https?://\S+/install\.sh\b.*\|\s*(ba)?sh", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*npx\s+skills\s+add\s+\S+(\s|$)", re.IGNORECASE),
    re.compile(r"(^|&&|\|\|)\s*[A-Za-z0-9_.-]+\s+skills\s+add(\s|$)", re.IGNORECASE),
)

BOOTSTRAP_FILENAME = "telegram_ai_bot_cli_bootstrap.txt"
DEFAULT_BOOTSTRAP_PATH = f"/data/{BOOTSTRAP_FILENAME}"


def _bootstrap_file() -> Path:
    raw = (os.getenv("CLI_BOOTSTRAP_PATH", DEFAULT_BOOTSTRAP_PATH) or "").strip()
    path = Path(raw or DEFAULT_BOOTSTRAP_PATH).expanduser()
    if (path.exists() and path.is_dir()) or raw.endswith(("/", "\\")):
        return path / BOOTSTRAP_FILENAME
    return path


def _is_install_command(command: str) -> bool:
    text = (command or "").strip()
    return bool(text) and any(pattern.search(text) for pattern in INSTALL_PATTERNS)


def persist_install_command(command: str) -> str | None:
    text = (command or "").strip()
    if not _is_install_command(text):
        return None
    path = _bootstrap_file()
    try:
        existing = [line.strip() for line in path.read_text("utf-8", errors="ignore").splitlines()] if path.exists() else []
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
