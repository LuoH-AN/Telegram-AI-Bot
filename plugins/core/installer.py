"""Plugin installer — GitHub URL and local path installation with S3 persistence."""

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

S3_BUCKET = "skills"
S3_STATE_KEY = "installed_skills.json"


def _ensure_plugin_dir() -> Path:
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLED_MARKER.mkdir(parents=True, exist_ok=True)
    return PLUGIN_DIR


def _get_s3_backend():
    """Get S3 backend if available."""
    try:
        from plugins.s3.hf_backend import get_available_backend
        backend = get_available_backend()
        if backend.enabled:
            return backend
    except Exception:
        pass
    return None


def _load_skill_registry() -> dict:
    """Load installed skills registry from S3."""
    backend = _get_s3_backend()
    if not backend:
        return {}

    try:
        from plugins.s3.engine import S3Service
        svc = S3Service(0, backend)
        svc.load()
        bucket = svc._buckets.get(S3_BUCKET)
        if bucket:
            obj = bucket.objects.get(S3_STATE_KEY)
            if obj:
                data = backend.get_object(0, obj.storage_path, allow_plaintext=True)
                if data:
                    return json.loads(data.decode("utf-8"))
    except Exception as e:
        logger.debug("Failed to load skill registry from S3: %s", e)

    return {}


def _save_skill_registry(registry: dict) -> bool:
    """Save installed skills registry to S3."""
    backend = _get_s3_backend()
    if not backend:
        return False

    try:
        from plugins.s3.engine import S3Service
        svc = S3Service(0, backend)
        svc.load()

        if S3_BUCKET not in svc._buckets:
            svc.create_bucket(S3_BUCKET)

        data = json.dumps(registry, ensure_ascii=False, indent=2).encode("utf-8")
        result = svc.put_object(S3_BUCKET, S3_STATE_KEY, data, content_type="application/json", encrypt=False)
        return result.get("ok", False)
    except Exception as e:
        logger.warning("Failed to save skill registry to S3: %s", e)
        return False


def _store_skill_files(name: str, plugin_dir: Path) -> bool:
    """Store skill files to S3."""
    backend = _get_s3_backend()
    if not backend:
        return False

    try:
        from plugins.s3.engine import S3Service
        svc = S3Service(0, backend)
        svc.load()

        if S3_BUCKET not in svc._buckets:
            svc.create_bucket(S3_BUCKET)

        for file_path in plugin_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(plugin_dir)
                key = f"skills/{name}/{rel_path}"

                with open(file_path, "rb") as f:
                    data = f.read()

                content_type = "text/plain"
                if file_path.suffix == ".py":
                    content_type = "text/x-python"
                elif file_path.suffix == ".json":
                    content_type = "application/json"
                elif file_path.suffix == ".md":
                    content_type = "text/markdown"

                svc.put_object(S3_BUCKET, key, data, content_type=content_type, encrypt=False)

        return True
    except Exception as e:
        logger.warning("Failed to store skill files to S3: %s", e)
        return False


def _restore_skill_files(name: str, plugin_dir: Path) -> bool:
    """Restore skill files from S3 to local directory."""
    backend = _get_s3_backend()
    if not backend:
        return False

    try:
        from plugins.s3.engine import S3Service
        svc = S3Service(0, backend)
        svc.load()

        bucket = svc._buckets.get(S3_BUCKET)
        if not bucket:
            return False

        prefix = f"skills/{name}/"
        for key, obj in bucket.objects.items():
            if key.startswith(prefix):
                data = backend.get_object(0, obj.storage_path, allow_plaintext=True)
                if data:
                    rel_path = key[len(prefix):]
                    file_path = plugin_dir / rel_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(data)

        return True
    except Exception as e:
        logger.warning("Failed to restore skill files from S3: %s", e)
        return False


def _delete_skill_files(name: str) -> bool:
    """Delete skill files from S3."""
    backend = _get_s3_backend()
    if not backend:
        return False

    try:
        from plugins.s3.engine import S3Service
        svc = S3Service(0, backend)
        svc.load()

        bucket = svc._buckets.get(S3_BUCKET)
        if not bucket:
            return True

        prefix = f"skills/{name}/"
        keys_to_delete = [k for k in bucket.objects.keys() if k.startswith(prefix)]
        for key in keys_to_delete:
            svc.delete_object(S3_BUCKET, key)

        return True
    except Exception as e:
        logger.warning("Failed to delete skill files from S3: %s", e)
        return False


def sync_skills_from_s3() -> list[str]:
    """Sync installed skills from S3 to local directory. Returns list of skill names."""
    registry = _load_skill_registry()
    if not registry:
        return []

    _ensure_plugin_dir()
    restored = []

    for name, info in registry.get("skills", {}).items():
        plugin_dir = PLUGIN_DIR / name
        if _restore_skill_files(name, plugin_dir):
            marker = INSTALLED_MARKER / f"{name}.json"
            marker.write_text(json.dumps(info, ensure_ascii=False))
            restored.append(name)
            logger.info("Restored skill '%s' from S3", name)

    return restored


def sync_skills_to_s3() -> int:
    """Sync all local installed skills to S3. Returns count synced."""
    registry = {"skills": {}}

    if INSTALLED_MARKER.is_dir():
        for marker in INSTALLED_MARKER.glob("*.json"):
            try:
                info = json.loads(marker.read_text(encoding="utf-8"))
                name = info.get("name")
                if name:
                    registry["skills"][name] = info
            except Exception:
                pass

    if not registry["skills"]:
        return 0

    _save_skill_registry(registry)
    count = 0

    for name in registry["skills"].keys():
        plugin_dir = PLUGIN_DIR / name
        if plugin_dir.is_dir():
            if _store_skill_files(name, plugin_dir):
                count += 1

    return count


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

    info = {"name": name, "source": source, "version": manifest.version}
    marker = INSTALLED_MARKER / f"{name}.json"
    marker.write_text(json.dumps(info, ensure_ascii=False))

    _store_skill_files(name, plugin_dir)

    registry = _load_skill_registry()
    if "skills" not in registry:
        registry["skills"] = {}
    registry["skills"][name] = info
    _save_skill_registry(registry)

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

    _delete_skill_files(name)

    registry = _load_skill_registry()
    if name in registry.get("skills", {}):
        del registry["skills"][name]
        _save_skill_registry(registry)

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
