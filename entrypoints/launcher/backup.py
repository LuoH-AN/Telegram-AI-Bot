"""Periodic /data backup to /backup, and startup restore.

Persistence model for ephemeral containers (e.g. HF Spaces):
  /data    — runtime-generated state (CLI bootstrap, installed plugins). Ephemeral
             by default; survives in-process restarts but NOT container rebuilds.
  /backup  — a directory the operator keeps persistent (e.g. HF Space persistent
             storage mounted here). Only this survives rebuilds.

This module snapshots /data into /backup/data.zip on an interval (last snapshot
wins — older ones are overwritten), and restores /data from the latest snapshot
at startup. BACKUP_* env vars tune the behavior.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("BACKUP_DATA_DIR", "/data"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/backup"))
BACKUP_FILE = BACKUP_DIR / os.getenv("BACKUP_FILENAME", "data.zip")
INTERVAL = max(30.0, float(os.getenv("BACKUP_INTERVAL_SECONDS", "600")))


def _enabled() -> bool:
    return (os.getenv("BACKUP_ENABLED", "1") or "1").strip().lower() in {"1", "true", "yes", "on", "y"}


def _snapshot() -> bool:
    """Zip /data into /backup/data.zip (atomic via temp rename). Returns True on success."""
    if not DATA_DIR.is_dir():
        return False
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = BACKUP_FILE.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp_file, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(DATA_DIR.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(DATA_DIR))
        os.replace(tmp_file, BACKUP_FILE)
        logger.info("backup: snapshot saved (%d bytes) -> %s", BACKUP_FILE.stat().st_size, BACKUP_FILE)
        return True
    except Exception:
        logger.warning("backup: snapshot failed", exc_info=True)
        tmp_file.unlink(missing_ok=True)
        return False


def restore() -> bool:
    """Unzip /backup/data.zip into /data at startup. Returns True if a restore happened."""
    if not _enabled() or not BACKUP_FILE.is_file():
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("backup: restoring %s -> %s", BACKUP_FILE, DATA_DIR)
    try:
        with zipfile.ZipFile(BACKUP_FILE) as archive:
            members = archive.namelist()
            archive.extractall(DATA_DIR)
        logger.info("backup: restored %d entries", len(members))
        return True
    except Exception:
        logger.warning("backup: restore failed", exc_info=True)
        return False


def start_daemon() -> None:
    """Run periodic snapshots in a daemon thread (no-op if disabled)."""
    if not _enabled():
        logger.info("backup daemon disabled (BACKUP_ENABLED=0)")
        return

    def _loop() -> None:
        while True:
            _snapshot()
            time.sleep(INTERVAL)

    threading.Thread(target=_loop, daemon=True, name="data-backup").start()
    logger.info("backup daemon started: every %.0fs, %s -> %s", INTERVAL, DATA_DIR, BACKUP_FILE)
