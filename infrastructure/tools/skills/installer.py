"""Skill installer — GitHub URL and local path installation."""

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

from .manifest import SKILL_FILENAME, SKILL_NAME_RE, load_manifest

logger = logging.getLogger(__name__)
PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "/data/plugins"))
INSTALLED_MARKER = PLUGIN_DIR / ".installed"


def _ensure_dir() -> Path:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLED_MARKER.mkdir(parents=True, exist_ok=True)
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
    dest = PLUGIN_DIR / name
    url = f"https://github.com/{owner_repo}/archive/refs/heads/{branch}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "TGBot"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        prefix = f"{name}-{branch}/{subdir}/" if subdir else f"{name}-{branch}/"
        for member in zf.namelist():
            if member.startswith(prefix):
                rel = member[len(prefix):].lstrip("/")
                if rel and not member.endswith("/"):
                    fp = dest / rel
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_bytes(zf.read(member))
    return dest


def _finalize(plugin_dir: Path, source: str) -> dict:
    plugin_dir = plugin_dir.resolve()
    plugin_root = PLUGIN_DIR.resolve()
    if plugin_dir.parent != plugin_root:
        return {"ok": False, "message": "Plugin staging path escapes plugin directory"}
    manifest = load_manifest(plugin_dir, is_builtin=False)
    if not manifest:
        shutil.rmtree(plugin_dir, ignore_errors=True)
        return {"ok": False, "message": f"No {SKILL_FILENAME}"}
    name = manifest.name
    if plugin_dir.name != name:
        new_dir = _safe_child(PLUGIN_DIR, name)
        if new_dir.exists():
            shutil.rmtree(new_dir)
        shutil.move(str(plugin_dir), str(new_dir))
        plugin_dir = new_dir
    info = {"name": name, "source": source, "version": manifest.version}
    marker = _safe_child(INSTALLED_MARKER, name).with_suffix(".json")
    marker.write_text(json.dumps(info, ensure_ascii=False))
    logger.info("Installed '%s'", name)
    return {"ok": True, "name": name, "path": str(plugin_dir)}


def install_from_github(url: str) -> dict:
    try:
        owner_repo, subdir = _parse_url(url)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    _ensure_dir()
    for branch in ("main", "master"):
        try:
            return _finalize(_download(owner_repo, branch, subdir), url)
        except Exception:
            continue
    return {"ok": False, "message": "Download failed"}


def install_from_local(path: str | Path) -> dict:
    src = Path(path).resolve()
    if not src.is_dir() or not (src / SKILL_FILENAME).is_file():
        return {"ok": False, "message": f"Invalid: {src}"}
    _ensure_dir()
    dest = PLUGIN_DIR / src.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return _finalize(dest, str(src))


def uninstall(name: str) -> dict:
    try:
        plugin_dir = _safe_child(PLUGIN_DIR, name)
        marker = _safe_child(INSTALLED_MARKER, name).with_suffix(".json")
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    if not plugin_dir.exists():
        return {"ok": False, "message": f"'{name}' not found"}
    shutil.rmtree(plugin_dir)
    marker.unlink(missing_ok=True)
    logger.info("Uninstalled '%s'", name)
    return {"ok": True, "name": name}


def list_installed() -> list[dict]:
    if not INSTALLED_MARKER.is_dir():
        return []
    return [json.loads(m.read_text()) for m in INSTALLED_MARKER.glob("*.json")]
