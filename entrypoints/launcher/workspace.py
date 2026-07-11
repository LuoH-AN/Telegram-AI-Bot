"""Activate a complete application workspace stored inside persistent /data."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def active_workspace() -> Path:
    configured = (os.getenv("TERMINAL_WORKSPACE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    data_root = Path(os.getenv("BACKUP_DATA_DIR", "/data")).expanduser().resolve()
    return data_root / "telegram_ai_bot" / "workspace"


def prepare_active_workspace(packaged_root: Path) -> Path:
    """Create the persistent workspace once without overwriting restored work."""
    packaged = packaged_root.resolve()
    active = active_workspace()
    if active == packaged:
        return active
    if not active.exists():
        active.parent.mkdir(parents=True, exist_ok=True)
        staging = active.with_name(active.name + ".initializing")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(packaged, staging, symlinks=True)
        os.replace(staging, active)
    elif not (active / "entrypoints" / "main.py").is_file():
        shutil.copytree(packaged, active, dirs_exist_ok=True, symlinks=True)
    return active


def exec_active_workspace(packaged_root: Path) -> None:
    """Re-exec the launcher from /data when currently running image code."""
    active = prepare_active_workspace(packaged_root)
    if packaged_root.resolve() == active.resolve():
        return
    env = os.environ.copy()
    env["_TGBOT_ACTIVE_WORKSPACE"] = str(active)
    env.setdefault("_TGBOT_PACKAGED_ROOT", str(packaged_root.resolve()))
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(active), existing) if part)
    os.chdir(active)
    os.execve(sys.executable, [sys.executable, "-m", "entrypoints.main"], env)
