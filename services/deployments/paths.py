"""Filesystem helpers for deployment storage."""

from __future__ import annotations

from pathlib import Path

from .slug import normalize_slug

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ROOT = REPO_ROOT / "runtime" / "deployments"
SKIP_NAMES = {".git", ".deploy.json", "__pycache__", "node_modules"}


def ensure_deploy_root() -> Path:
    DEPLOY_ROOT.mkdir(parents=True, exist_ok=True)
    return DEPLOY_ROOT


def deployment_dir(slug: str) -> Path:
    return ensure_deploy_root() / normalize_slug(slug)


def manifest_path(slug: str) -> Path:
    return deployment_dir(slug) / ".deploy.json"


def resolve_source_path(raw_path: str) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        raise ValueError("source_path is required")
    target = Path(text)
    full_path = target if target.is_absolute() else (REPO_ROOT / target)
    full_path = full_path.resolve()
    if full_path != REPO_ROOT and REPO_ROOT not in full_path.parents:
        raise ValueError("source_path must stay inside repository root")
    if DEPLOY_ROOT in full_path.parents or full_path == DEPLOY_ROOT:
        raise ValueError("cannot deploy directly from runtime/deployments")
    if not full_path.exists():
        raise FileNotFoundError(full_path)
    return full_path


def safe_child(root: Path, relative_path: str) -> Path:
    target = (root / str(relative_path or "").strip()).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path escapes deployment root")
    return target
