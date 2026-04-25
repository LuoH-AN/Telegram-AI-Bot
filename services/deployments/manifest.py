"""Deployment metadata helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from config import WEB_BASE_URL

from .path import manifest_path
from .slug import normalize_slug


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def deployment_url(slug: str, entry_path: str = "index.html") -> str:
    base = f"{WEB_BASE_URL.rstrip('/')}/deploy/{normalize_slug(slug)}"
    return f"{base}/" if not entry_path or entry_path == "index.html" else f"{base}/{entry_path.lstrip('/')}"


def load_manifest(slug: str) -> dict | None:
    path = manifest_path(slug)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


def save_manifest(slug: str, data: dict) -> dict:
    payload = dict(data)
    payload["slug"] = normalize_slug(slug)
    payload["url"] = deployment_url(payload["slug"], payload.get("entry_path") or "index.html")
    path = manifest_path(payload["slug"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
