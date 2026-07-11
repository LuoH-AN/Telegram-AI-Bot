"""Persistent proot filesystem: every terminal write lands below /data."""

from __future__ import annotations

import fcntl
import os
import shutil
import tarfile
from pathlib import Path

from shared.terminal_environment import persistent_terminal_root


class TerminalRootfsError(RuntimeError):
    pass


def filesystem_mode() -> str:
    return (os.getenv("TERMINAL_FILESYSTEM_MODE", "proot") or "proot").strip().lower()


def rootfs_dir() -> Path:
    return persistent_terminal_root() / "rootfs"


def seed_archive() -> Path:
    return Path(os.getenv("TERMINAL_ROOTFS_SEED", "/opt/telegram-terminal-rootfs.tar.gz")).expanduser()


def _persistent_workspace() -> Path:
    configured = (os.getenv("TERMINAL_WORKSPACE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    data_root = Path(os.getenv("BACKUP_DATA_DIR", "/data")).expanduser().resolve()
    return data_root / "telegram_ai_bot" / "workspace"


def _validate_archive(archive: tarfile.TarFile) -> None:
    for member in archive.getmembers():
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise TerminalRootfsError(f"unsafe rootfs seed member: {member.name}")


def ensure_rootfs() -> Path | None:
    mode = filesystem_mode()
    if mode == "host":
        return None
    if mode != "proot":
        raise TerminalRootfsError("TERMINAL_FILESYSTEM_MODE must be 'proot' or explicit unsafe test mode 'host'")
    if not shutil.which("proot"):
        raise TerminalRootfsError("proot is unavailable; rebuild the image before using the persistent terminal")
    seed = seed_archive()
    if not seed.is_file():
        raise TerminalRootfsError(f"terminal rootfs seed is missing: {seed}; rebuild the image")

    root = rootfs_dir()
    marker = root / ".telegram-rootfs-ready"
    if marker.is_file():
        return root
    root.parent.mkdir(parents=True, exist_ok=True)
    lock_path = root.parent / ".rootfs-initialize.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if marker.is_file():
            return root
        staging = root.with_name(root.name + ".initializing")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        try:
            with tarfile.open(seed, "r:*") as archive:
                _validate_archive(archive)
                archive.extractall(staging)
            for directory in ("dev", "proc", "sys", "tmp", "run", "data", "backup"):
                (staging / directory).mkdir(parents=True, exist_ok=True)
            # Preserve compatibility with commands that still reference the
            # image's old APP_DIR while making their writes hit /data.
            legacy_app = Path(os.getenv("APP_DIR", "/opt/telegram-ai-bot"))
            if legacy_app.is_absolute():
                legacy_target = staging / legacy_app.relative_to("/")
                if legacy_target.is_symlink() or legacy_target.is_file():
                    legacy_target.unlink(missing_ok=True)
                elif legacy_target.is_dir():
                    shutil.rmtree(legacy_target)
                legacy_target.parent.mkdir(parents=True, exist_ok=True)
                legacy_target.symlink_to(_persistent_workspace())
            (staging / ".telegram-rootfs-ready").write_text("1\n", encoding="utf-8")
            os.replace(staging, root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return root


def terminal_command(command: str, cwd: Path) -> list[str]:
    root = ensure_rootfs()
    if root is None:
        return ["/bin/bash", "-lc", command]
    proot = shutil.which("proot")
    bindings: list[str] = []
    for path in (Path("/dev"), Path("/proc"), Path("/sys"), Path("/data"), Path("/backup")):
        if path.exists():
            bindings.extend(["-b", str(path)])
    return [
        str(proot),
        "-0",
        "-r",
        str(root),
        *bindings,
        "-w",
        str(cwd),
        "/bin/bash",
        "-lc",
        command,
    ]
