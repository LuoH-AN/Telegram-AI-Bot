"""Deployment listing and deletion."""

from __future__ import annotations

import shutil

from .manifest import deployment_url, load_manifest
from .path import DEPLOY_ROOT, deployment_dir, ensure_deploy_root
from .slug import normalize_slug


def list_deployments() -> list[dict]:
    ensure_deploy_root()
    items: list[dict] = []
    for path in sorted(DEPLOY_ROOT.iterdir()):
        if not path.is_dir():
            continue
        manifest = load_manifest(path.name) or {"slug": path.name, "entry_path": "index.html"}
        manifest.setdefault("url", deployment_url(path.name, manifest.get("entry_path") or "index.html"))
        items.append(manifest)
    return items


def get_deployment(slug: str) -> dict | None:
    return load_manifest(normalize_slug(slug))


def delete_deployment(slug: str) -> bool:
    target = deployment_dir(slug)
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True
