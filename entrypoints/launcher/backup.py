"""Periodic /data backup to /backup, and startup restore.

Persistence model for ephemeral containers (e.g. HF Spaces):
  /data    — complete runtime-generated state, including terminal HOME,
             dependencies, caches, temporary files, CLI bootstrap and plugins. Ephemeral
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
import stat
import threading
import time
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("BACKUP_DATA_DIR", "/data"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/backup"))
BACKUP_FILE = BACKUP_DIR / os.getenv("BACKUP_FILENAME", "data.zip")
_workspace_raw = (os.getenv("BACKUP_TERMINAL_WORKSPACE") or "").strip()
WORKSPACE_DIR: Path | None = Path(_workspace_raw).expanduser().resolve() if _workspace_raw else Path(__file__).resolve().parents[2]
INTERVAL = max(30.0, float(os.getenv("BACKUP_INTERVAL_SECONDS", "600")))
REQUEST_FILE = DATA_DIR / ".telegram-ai-bot-backup-request"
_SNAPSHOT_LOCK = threading.Lock()


def _enabled() -> bool:
    return (os.getenv("BACKUP_ENABLED", "1") or "1").strip().lower() in {"1", "true", "yes", "on", "y"}


def request_snapshot() -> None:
    """Coalesce a cross-process request for a near-immediate full snapshot."""
    if not _enabled():
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        REQUEST_FILE.touch(exist_ok=True)
    except OSError:
        logger.warning("backup: could not request snapshot", exc_info=True)


def _zip_info(path: Path, arcname: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname)
    info.create_system = 3
    info.external_attr = (path.lstat().st_mode & 0xFFFF) << 16
    return info


def _archive_tree(archive: zipfile.ZipFile, root: Path, current: Path, *, prefix: str = "") -> None:
    """Archive every entry without ignore rules, preserving dirs and symlinks."""
    with os.scandir(current) as entries:
        for entry in sorted(entries, key=lambda item: item.name):
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            arcname = f"{prefix}{relative}"
            if entry.is_symlink():
                archive.writestr(_zip_info(path, arcname), os.readlink(path))
            elif entry.is_dir(follow_symlinks=False):
                archive.write(path, arcname=f"{arcname}/")
                _archive_tree(archive, root, path, prefix=prefix)
            elif entry.is_file(follow_symlinks=False):
                archive.write(path, arcname=arcname)
            else:
                # Runtime sockets/devices cannot be meaningfully reconstructed;
                # keep their metadata in the archive instead of silently hiding them.
                special = _zip_info(path, f".terminal-special/{arcname}.metadata")
                special.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(special, f"mode={path.lstat().st_mode}\n")


def _snapshot() -> bool:
    """Zip the complete data tree atomically, with no dependency ignore list."""
    if not DATA_DIR.is_dir():
        return False
    with _SNAPSHOT_LOCK:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        tmp_file = BACKUP_FILE.with_suffix(".zip.tmp")
        try:
            with zipfile.ZipFile(tmp_file, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                _archive_tree(archive, DATA_DIR, DATA_DIR)
                if WORKSPACE_DIR and WORKSPACE_DIR.is_dir():
                    workspace = WORKSPACE_DIR.resolve()
                    data = DATA_DIR.resolve()
                    if workspace != data and data not in workspace.parents and workspace not in data.parents:
                        _archive_tree(
                            archive,
                            workspace,
                            workspace,
                            prefix="__telegram_backup_roots__/workspace/",
                        )
            os.replace(tmp_file, BACKUP_FILE)
            logger.info("backup: complete snapshot saved (%d bytes) -> %s", BACKUP_FILE.stat().st_size, BACKUP_FILE)
            return True
        except Exception:
            logger.warning("backup: snapshot failed", exc_info=True)
            tmp_file.unlink(missing_ok=True)
            return False


def _safe_target(name: str) -> Path:
    workspace_prefix = "__telegram_backup_roots__/workspace/"
    if name.startswith(workspace_prefix):
        if WORKSPACE_DIR is None:
            raise ValueError("backup contains a workspace but no restore workspace is configured")
        root = WORKSPACE_DIR.resolve()
        relative = Path(name[len(workspace_prefix):])
    else:
        root = DATA_DIR.resolve()
        relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe backup member: {name}")
    target = (root / relative).resolve(strict=False)
    if target != root and root not in target.parents:
        raise ValueError(f"backup member escapes data directory: {name}")
    return target


def _remove_conflict(path: Path, *, want_directory: bool = False) -> None:
    if path.is_symlink() or (path.exists() and not (want_directory and path.is_dir())):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _restore_zip(archive: zipfile.ZipFile) -> int:
    members = archive.infolist()
    # Directories first, then regular files, then links. This prevents a link
    # from redirecting extraction of a later member outside DATA_DIR.
    for info in members:
        if "/.terminal-special/" in f"/{info.filename}" or info.filename.startswith(".terminal-special/"):
            continue
        mode = (info.external_attr >> 16) & 0xFFFF
        if info.is_dir() or stat.S_ISDIR(mode):
            target = _safe_target(info.filename.rstrip("/"))
            _remove_conflict(target, want_directory=True)
            target.mkdir(parents=True, exist_ok=True)
            if mode:
                os.chmod(target, stat.S_IMODE(mode))
    for info in members:
        if "/.terminal-special/" in f"/{info.filename}" or info.filename.startswith(".terminal-special/"):
            continue
        mode = (info.external_attr >> 16) & 0xFFFF
        if info.is_dir() or stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            continue
        target = _safe_target(info.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        _remove_conflict(target)
        with archive.open(info) as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        if mode:
            os.chmod(target, stat.S_IMODE(mode))
    for info in members:
        mode = (info.external_attr >> 16) & 0xFFFF
        if not stat.S_ISLNK(mode):
            continue
        target = _safe_target(info.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        _remove_conflict(target)
        target.symlink_to(archive.read(info).decode("utf-8"))
    return len(members)


def restore() -> bool:
    """Unzip /backup/data.zip into /data at startup. Returns True if a restore happened."""
    if not _enabled() or not BACKUP_FILE.is_file():
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("backup: restoring %s -> %s", BACKUP_FILE, DATA_DIR)
    try:
        with zipfile.ZipFile(BACKUP_FILE) as archive:
            restored = _restore_zip(archive)
        logger.info("backup: restored %d entries", restored)
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
        next_periodic = 0.0
        while True:
            now = time.monotonic()
            requested = REQUEST_FILE.exists()
            if requested or now >= next_periodic:
                REQUEST_FILE.unlink(missing_ok=True)
                _snapshot()
                next_periodic = time.monotonic() + INTERVAL
            time.sleep(1)

    threading.Thread(target=_loop, daemon=True, name="data-backup").start()
    logger.info("backup daemon started: every %.0fs, %s -> %s", INTERVAL, DATA_DIR, BACKUP_FILE)
