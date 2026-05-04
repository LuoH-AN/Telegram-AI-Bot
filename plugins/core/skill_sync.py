"""S3 persistence for installed skills."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
BUCKET, STATE_KEY = "skills", "installed_skills.json"


def _backend():
    try:
        from plugins.s3.hf_backend import get_available_backend
        b = get_available_backend()
        return b if b and b.enabled else None
    except Exception:
        return None


def _svc():
    from plugins.s3.engine import S3Service
    b = _backend()
    return S3Service(0, b) if b else None


def _registry(load: bool = True, data: dict | None = None) -> dict | bool:
    svc = _svc()
    if not svc:
        return {} if load else False
    try:
        svc.load()
        if load:
            bucket = svc._buckets.get(BUCKET)
            if bucket and STATE_KEY in bucket.objects:
                obj = bucket.objects[STATE_KEY]
                d = _backend().get_object(0, obj.storage_path, allow_plaintext=True)
                return json.loads(d.decode()) if d else {}
            return {}
        if BUCKET not in svc._buckets:
            svc.create_bucket(BUCKET)
        return svc.put_object(BUCKET, STATE_KEY, json.dumps(data, ensure_ascii=False).encode(), content_type="application/json", encrypt=False).get("ok", False)
    except Exception as e:
        logger.warning("Registry op failed: %s", e)
        return {} if load else False


def _store(name: str, plugin_dir: Path) -> bool:
    svc = _svc()
    if not svc:
        return False
    try:
        svc.load()
        if BUCKET not in svc._buckets:
            svc.create_bucket(BUCKET)
        for fp in plugin_dir.rglob("*"):
            if fp.is_file():
                key = f"skills/{name}/{fp.relative_to(plugin_dir)}"
                ct = {"py": "text/x-python", "json": "application/json", "md": "text/markdown"}.get(fp.suffix[1:], "text/plain")
                svc.put_object(BUCKET, key, fp.read_bytes(), content_type=ct, encrypt=False)
        return True
    except Exception as e:
        logger.warning("Store failed: %s", e)
        return False


def _restore(name: str, dest: Path) -> bool:
    b, svc = _backend(), _svc()
    if not b or not svc:
        return False
    try:
        svc.load()
        bucket = svc._buckets.get(BUCKET)
        if not bucket:
            return False
        for key, obj in bucket.objects.items():
            if key.startswith(f"skills/{name}/"):
                d = b.get_object(0, obj.storage_path, allow_plaintext=True)
                if d:
                    fp = dest / key[len(f"skills/{name}/"):]
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_bytes(d)
        return True
    except Exception as e:
        logger.warning("Restore failed: %s", e)
        return False


def _delete(name: str) -> bool:
    svc = _svc()
    if not svc:
        return False
    try:
        svc.load()
        for k in [x for x in svc._buckets.get(BUCKET, {}).objects if x.startswith(f"skills/{name}/")]:
            svc.delete_object(BUCKET, k)
        return True
    except Exception as e:
        logger.warning("Delete failed: %s", e)
        return False


def sync_from_s3(plugin_dir: Path, marker_dir: Path) -> list[str]:
    r = _registry()
    return [n for n, i in r.get("skills", {}).items() if _restore(n, plugin_dir / n) and (marker_dir / f"{n}.json").write_text(json.dumps(i, ensure_ascii=False)) or True]


def persist_skill(name: str, plugin_dir: Path, info: dict) -> None:
    _store(name, plugin_dir)
    r = _registry()
    r.setdefault("skills", {})[name] = info
    _registry(False, r)


def remove_skill(name: str) -> None:
    _delete(name)
    r = _registry()
    r.get("skills", {}).pop(name, None)
    _registry(False, r)