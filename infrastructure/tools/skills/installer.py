"""Skill installer — GitHub URL and local path installation."""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .manifest import SKILL_FILENAME, SKILL_NAME_RE, load_manifest

logger = logging.getLogger(__name__)
PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "/data/plugins"))
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_FILES = 2000


def _ensure_dir() -> Path:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    return PLUGIN_DIR


def _safe_child(root: Path, name: str) -> Path:
    if not SKILL_NAME_RE.fullmatch(name or ""):
        raise ValueError(f"Unsafe skill name: {name!r}")
    resolved_root = root.resolve()
    target = (resolved_root / name).resolve()
    if target.parent != resolved_root:
        raise ValueError(f"Skill path escapes plugin directory: {name!r}")
    return target


def _parse_url(url: str) -> tuple[str, str]:
    match = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/[^/]+/([^/]+))?", url)
    if match:
        return f"{match.group(1)}/{match.group(2)}", match.group(3) or ""
    if "/" in url and not url.startswith("http"):
        parts = url.split("/")
        return "/".join(parts[:2]), "/".join(parts[2:])
    raise ValueError(f"Invalid URL: {url}")


def _download(owner_repo: str, branch: str, subdir: str) -> Path:
    name = owner_repo.split("/")[1]
    _ensure_dir()
    dest = Path(tempfile.mkdtemp(prefix=".skill-staging-", dir=str(PLUGIN_DIR)))
    url = f"https://github.com/{owner_repo}/archive/refs/heads/{branch}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "TGBot"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError(f"Skill archive exceeds {MAX_ARCHIVE_BYTES} bytes")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_FILES:
                raise ValueError(f"Skill archive contains too many entries ({len(infos)})")
            prefix = f"{name}-{branch}/{subdir.strip('/')}/" if subdir else f"{name}-{branch}/"
            extracted = 0
            for info in infos:
                member = info.filename
                if not member.startswith(prefix) or info.is_dir():
                    continue
                rel = member[len(prefix):].lstrip("/")
                rel_path = Path(rel)
                if not rel or rel_path.is_absolute() or ".." in rel_path.parts:
                    raise ValueError(f"Unsafe archive path: {member}")
                if info.file_size > MAX_FILE_BYTES:
                    raise ValueError(f"Skill file too large: {rel}")
                extracted += info.file_size
                if extracted > MAX_EXTRACTED_BYTES:
                    raise ValueError("Skill archive expands beyond the allowed size")
                fp = (dest / rel_path).resolve()
                if dest.resolve() not in fp.parents:
                    raise ValueError(f"Archive path escapes staging directory: {member}")
                fp.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, fp.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        return dest
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def _finalize(plugin_dir: Path, *, transactional: bool = False) -> dict:
    plugin_dir = plugin_dir.resolve()
    plugin_root = PLUGIN_DIR.resolve()
    if plugin_dir.parent != plugin_root:
        return {"ok": False, "message": "Plugin staging path escapes plugin directory"}
    manifest = load_manifest(plugin_dir, is_builtin=False)
    if not manifest:
        shutil.rmtree(plugin_dir, ignore_errors=True)
        return {"ok": False, "message": f"No {SKILL_FILENAME}"}
    name = manifest.name
    target = _safe_child(PLUGIN_DIR, name)
    backup_root: Path | None = None
    backup_path: Path | None = None
    try:
        if target.exists() and target != plugin_dir:
            backup_root = Path(tempfile.mkdtemp(prefix=".skill-backup-", dir=str(PLUGIN_DIR)))
            backup_path = backup_root / name
            shutil.move(str(target), str(backup_path))
        if plugin_dir != target:
            shutil.move(str(plugin_dir), str(target))
        plugin_dir = target
    except Exception:
        if target.exists() and target != backup_path:
            shutil.rmtree(target, ignore_errors=True)
        if backup_path and backup_path.exists():
            shutil.move(str(backup_path), str(target))
        if backup_root:
            shutil.rmtree(backup_root, ignore_errors=True)
        raise
    logger.info("Installed '%s'", name)
    result = {
        "ok": True,
        "name": name,
        "path": str(plugin_dir),
        "_backup_root": str(backup_root) if backup_root else "",
        "_backup_path": str(backup_path) if backup_path else "",
    }
    if not transactional:
        commit_install(result)
    return result


def commit_install(result: dict) -> None:
    backup_root = Path(result.get("_backup_root") or "") if result.get("_backup_root") else None
    if backup_root:
        shutil.rmtree(backup_root, ignore_errors=True)


def rollback_install(result: dict) -> dict:
    """Undo a finalized install when hot-load or user registration fails."""
    try:
        name = str(result["name"])
        target = _safe_child(PLUGIN_DIR, name)
        backup_path = Path(result.get("_backup_path") or "") if result.get("_backup_path") else None
        backup_root = Path(result.get("_backup_root") or "") if result.get("_backup_root") else None
        shutil.rmtree(target, ignore_errors=True)
        if backup_path and backup_path.exists():
            shutil.move(str(backup_path), str(target))
        if backup_root:
            shutil.rmtree(backup_root, ignore_errors=True)
        return {"ok": True, "name": name}
    except Exception as exc:
        logger.exception("Failed to roll back skill install")
        return {"ok": False, "message": str(exc)}


def install_from_github(url: str, *, transactional: bool = False) -> dict:
    try:
        owner_repo, subdir = _parse_url(url)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    _ensure_dir()
    for branch in ("main", "master"):
        try:
            return _finalize(_download(owner_repo, branch, subdir), transactional=transactional)
        except Exception as exc:
            logger.warning("Skill download failed for %s@%s: %s", owner_repo, branch, exc)
            continue
    return {"ok": False, "message": "Download failed"}


def install_from_local(path: str | Path, *, transactional: bool = False) -> dict:
    src = Path(path).resolve()
    if not src.is_dir() or not (src / SKILL_FILENAME).is_file():
        return {"ok": False, "message": f"Invalid: {src}"}
    _ensure_dir()
    staging = Path(tempfile.mkdtemp(prefix=".skill-staging-", dir=str(PLUGIN_DIR)))
    try:
        shutil.copytree(src, staging, dirs_exist_ok=True)
        return _finalize(staging, transactional=transactional)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def uninstall(name: str) -> dict:
    try:
        plugin_dir = _safe_child(PLUGIN_DIR, name)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    if not plugin_dir.exists():
        return {"ok": False, "message": f"'{name}' not found"}
    shutil.rmtree(plugin_dir)
    logger.info("Uninstalled '%s'", name)
    return {"ok": True, "name": name}
