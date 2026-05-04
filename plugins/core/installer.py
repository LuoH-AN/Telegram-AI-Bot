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
from .skill_sync import persist_skill, remove_skill, sync_from_s3

logger = logging.getLogger(__name__)
PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "runtime/plugins"))
INSTALLED_MARKER = PLUGIN_DIR / ".installed"


def _ensure_dir() -> Path:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLED_MARKER.mkdir(parents=True, exist_ok=True)
    return PLUGIN_DIR


def _parse_url(url: str) -> tuple[str, str]:
    m = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/[^/]+/([^/]+))?", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}", m.group(3) or ""
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
        for m in zf.namelist():
            if m.startswith(prefix):
                rel = m[len(prefix):].lstrip("/")
                if rel and not m.endswith("/"):
                    fp = dest / rel
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_bytes(zf.read(m))
    return dest


def _finalize(plugin_dir: Path, source: str) -> dict:
    m = load_manifest_from_path(plugin_dir, is_builtin=False)
    if not m:
        shutil.rmtree(plugin_dir, ignore_errors=True)
        return {"ok": False, "message": f"No {SKILL_FILENAME}"}
    name = m.name
    if plugin_dir.name != name:
        new_dir = PLUGIN_DIR / name
        if new_dir.exists():
            shutil.rmtree(new_dir)
        shutil.move(str(plugin_dir), str(new_dir))
        plugin_dir = new_dir
    info = {"name": name, "source": source, "version": m.version}
    (INSTALLED_MARKER / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False))
    persist_skill(name, plugin_dir, info)
    logger.info("Installed '%s'", name)
    return {"ok": True, "name": name, "path": str(plugin_dir)}


def install_from_github(url: str) -> dict:
    try:
        owner_repo, subdir = _parse_url(url)
    except ValueError as e:
        return {"ok": False, "message": str(e)}
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
    plugin_dir = PLUGIN_DIR / name
    if not plugin_dir.exists():
        return {"ok": False, "message": f"'{name}' not found"}
    shutil.rmtree(plugin_dir)
    (INSTALLED_MARKER / f"{name}.json").unlink(missing_ok=True)
    remove_skill(name)
    logger.info("Uninstalled '%s'", name)
    return {"ok": True, "name": name}


def list_installed() -> list[dict]:
    if not INSTALLED_MARKER.is_dir():
        return []
    return [json.loads(m.read_text()) for m in INSTALLED_MARKER.glob("*.json")]


def sync_skills_from_s3() -> list[str]:
    _ensure_dir()
    return sync_from_s3(PLUGIN_DIR, INSTALLED_MARKER)