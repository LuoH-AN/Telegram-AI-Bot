"""Plugin installer — GitHub URL and local path installation."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .manifest import SKILL_FILENAME, load_manifest_from_path

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "runtime/plugins"))
INSTALLED_MARKER = PLUGIN_DIR / ".installed"


def _ensure_plugin_dir() -> Path:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLED_MARKER.mkdir(parents=True, exist_ok=True)
    return PLUGIN_DIR


def _parse_github_url(url: str) -> tuple[str, str]:
    m = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/[^/]+/([^/]+))?(?:/.*)?$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}", m.group(3) or ""
    if "/" in url and not url.startswith("http"):
        parts = url.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:2]), "/".join(parts[2:])
    raise ValueError(f"Invalid GitHub URL or owner/repo: {url}")


def _download_github_archive(owner_repo: str, branch: str = "main", subdir: str = "") -> Path:
    archive_url = f"https://github.com/{owner_repo}/archive/refs/heads/{branch}.zip"
    name = owner_repo.split("/")[1]
    dest = PLUGIN_DIR / name
    logger.info("Downloading plugin from %s", archive_url)
    req = urllib.request.Request(archive_url, headers={"User-Agent": "Telegram-AI-Bot"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        prefix = f"{name}-{branch}/{subdir}/" if subdir else f"{name}-{branch}/"
        members = [m for m in zf.namelist() if m.startswith(prefix)]
        if not members:
            prefix = prefix.rstrip("/")
            members = [m for m in zf.namelist() if m.startswith(prefix)]
        for member in members:
            rel = member[len(prefix):].lstrip("/")
            if not rel or member.endswith("/"):
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))
    return dest


def _finalize(plugin_dir: Path, source: str) -> dict:
    manifest = load_manifest_from_path(plugin_dir, is_builtin=False)
    if not manifest:
        shutil.rmtree(plugin_dir, ignore_errors=True)
        return {"ok": False, "message": f"No {SKILL_FILENAME} found in {source}"}
    name = manifest.name
    if plugin_dir.name != name:
        new_dir = PLUGIN_DIR / name
        if new_dir.exists():
            shutil.rmtree(new_dir)
        shutil.move(str(plugin_dir), str(new_dir))
        plugin_dir = new_dir
    marker = INSTALLED_MARKER / f"{name}.json"
    marker.write_text(json.dumps({"name": name, "source": source, "version": manifest.version}, ensure_ascii=False))
    logger.info("Installed plugin '%s' from %s", name, source)
    return {"ok": True, "name": name, "path": str(plugin_dir)}


def install_from_github(url: str) -> dict:
    try:
        owner_repo, subdir = _parse_github_url(url)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    _ensure_plugin_dir()
    try:
        plugin_dir = _download_github_archive(owner_repo, "main", subdir)
    except Exception as exc:
        try:
            plugin_dir = _download_github_archive(owner_repo, "master", subdir)
        except Exception:
            return {"ok": False, "message": f"Failed to download: {exc}"}
    return _finalize(plugin_dir, url)


def install_from_local(path: str | Path) -> dict:
    src = Path(path).resolve()
    if not src.is_dir():
        return {"ok": False, "message": f"Not a directory: {src}"}
    if not (src / SKILL_FILENAME).is_file():
        return {"ok": False, "message": f"No {SKILL_FILENAME} found in {src}"}
    _ensure_plugin_dir()
    dest = PLUGIN_DIR / src.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return _finalize(dest, str(src))


def uninstall(name: str) -> dict:
    plugin_dir = PLUGIN_DIR / name
    if not plugin_dir.exists():
        return {"ok": False, "message": f"Plugin '{name}' not found in {PLUGIN_DIR}"}
    shutil.rmtree(plugin_dir)
    marker = INSTALLED_MARKER / f"{name}.json"
    if marker.exists():
        marker.unlink()
    logger.info("Uninstalled plugin '%s'", name)
    return {"ok": True, "name": name}


def list_installed() -> list[dict]:
    if not INSTALLED_MARKER.is_dir():
        return []
    result = []
    for marker in INSTALLED_MARKER.glob("*.json"):
        try:
            result.append(json.loads(marker.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result
