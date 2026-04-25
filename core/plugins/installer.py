"""Plugin installer — GitHub URL and local path installation."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
import urllib.request
import zipfile
import io

from .manifest import load_manifest_from_path, MANIFEST_FILENAME

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "runtime/plugins"))
INSTALLED_MARKER = PLUGIN_DIR / ".installed"


def _ensure_plugin_dir() -> Path:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLED_MARKER.mkdir(parents=True, exist_ok=True)
    return PLUGIN_DIR


def _parse_github_url(url: str) -> tuple[str, str]:
    """Extract owner/repo and optional subdir from a GitHub URL or bare owner/repo."""
    # Normalize various GitHub URL formats
    m = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/[^/]+/([^/]+))?(?:/.*)?$", url)
    if m:
        owner, repo = m.group(1), m.group(2)
        subdir = m.group(3) or ""
        return f"{owner}/{repo}", subdir
    if "/" in url and not url.startswith("http"):
        parts = url.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:2]), "/".join(parts[2:])
    raise ValueError(f"Invalid GitHub URL or owner/repo: {url}")


def _download_github_archive(owner_repo: str, branch: str = "main", subdir: str = "") -> Path:
    """Download a GitHub repo archive and extract it to runtime/plugins/<name>."""
    archive_url = f"https://github.com/{owner_repo}/archive/refs/heads/{branch}.zip"
    name = owner_repo.split("/")[1]
    dest = PLUGIN_DIR / name

    logger.info("Downloading plugin from %s", archive_url)
    req = urllib.request.Request(archive_url, headers={"User-Agent": "Telegram-AI-Bot"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        all_members = zf.namelist()
        # Filter to subdir if specified
        prefix = f"{name}-{branch}/"
        if subdir:
            prefix = f"{name}-{branch}/{subdir}/"
        members = [m for m in all_members if m.startswith(prefix)]
        if not members:
            # Try without trailing slash on subdir
            prefix_no_slash = prefix.rstrip("/")
            members = [m for m in all_members if m.startswith(prefix_no_slash)]
            prefix = prefix_no_slash

        # Extract
        for member in members:
            parts = member[len(prefix):].split("/", 1)
            if len(parts) == 1 and not member.endswith("/"):
                # File
                target = dest / parts[0]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))
            elif len(parts) > 1:
                # File inside directory
                target = dest / parts[1]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))

    return dest


def _extract_name_from_manifest(plugin_dir: Path) -> str | None:
    manifest = load_manifest_from_path(plugin_dir, is_builtin=False)
    return manifest.name if manifest else None


def install_from_github(url: str, name_hint: str = "") -> dict:
    """Install a plugin from a GitHub URL or owner/repo."""
    try:
        owner_repo, subdir = _parse_github_url(url)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    _ensure_plugin_dir()

    try:
        plugin_dir = _download_github_archive(owner_repo, branch="main", subdir=subdir)
    except Exception as exc:
        # Try main branch as fallback
        try:
            plugin_dir = _download_github_archive(owner_repo, branch="master", subdir=subdir)
        except Exception:
            return {"ok": False, "message": f"Failed to download: {exc}"}

    plugin_name = _extract_name_from_manifest(plugin_dir)
    if not plugin_name:
        # Fall back to name_hint or directory name
        plugin_name = name_hint.strip().lower() or plugin_dir.name
        # Rename directory
        new_dir = PLUGIN_DIR / plugin_name
        if new_dir.exists():
            shutil.rmtree(new_dir)
        if plugin_dir != new_dir:
            shutil.move(str(plugin_dir), str(new_dir))
        plugin_dir = new_dir

    # Write installed marker
    marker_file = INSTALLED_MARKER / f"{plugin_name}.json"
    marker_file.write_text(json.dumps({"name": plugin_name, "source": url, "version": "unknown"}, ensure_ascii=False))

    logger.info("Installed plugin '%s' from %s", plugin_name, url)
    return {"ok": True, "name": plugin_name, "path": str(plugin_dir)}


def install_from_local(path: str | Path) -> dict:
    """Copy a local plugin directory into runtime/plugins/."""
    src = Path(path).resolve()
    if not src.is_dir():
        return {"ok": False, "message": f"Not a directory: {src}"}

    manifest = load_manifest_from_path(src, is_builtin=False)
    if not manifest:
        return {"ok": False, "message": f"No manifest.json found in {src}"}

    _ensure_plugin_dir()
    dest = PLUGIN_DIR / manifest.name

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)

    marker_file = INSTALLED_MARKER / f"{manifest.name}.json"
    marker_file.write_text(json.dumps({"name": manifest.name, "source": str(src), "version": manifest.version}, ensure_ascii=False))

    logger.info("Installed plugin '%s' from local path %s", manifest.name, src)
    return {"ok": True, "name": manifest.name, "path": str(dest)}


def uninstall(name: str) -> dict:
    """Remove a plugin from runtime/plugins/."""
    plugin_dir = PLUGIN_DIR / name
    if not plugin_dir.exists():
        return {"ok": False, "message": f"Plugin '{name}' not found in {PLUGIN_DIR}"}

    shutil.rmtree(plugin_dir)

    marker_file = INSTALLED_MARKER / f"{name}.json"
    if marker_file.exists():
        marker_file.unlink()

    logger.info("Uninstalled plugin '%s'", name)
    return {"ok": True, "name": name}


def list_installed() -> list[dict]:
    """List all installed external plugins from the marker directory."""
    if not INSTALLED_MARKER.is_dir():
        return []
    result = []
    for marker_file in INSTALLED_MARKER.glob("*.json"):
        try:
            result.append(json.loads(marker_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result
