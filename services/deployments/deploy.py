"""Deploy static projects from files or directories."""

from __future__ import annotations

import shutil
from pathlib import Path

from .meta import load_manifest, now_iso, save_manifest
from .paths import REPO_ROOT, SKIP_NAMES, deployment_dir, resolve_source_path
from .slug import normalize_slug


def _copy_dir(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_NAMES))


def _entry_for_dir(dst: Path) -> str:
    index = dst / "index.html"
    if index.exists():
        return "index.html"
    html_files = sorted(path.relative_to(dst).as_posix() for path in dst.rglob("*.html") if path.is_file())
    if not html_files:
        raise ValueError("deployment source must contain index.html or another .html file")
    return html_files[0]


def deploy_from_path(source_path: str, *, slug: str = "") -> dict:
    src = resolve_source_path(source_path)
    site_slug = normalize_slug(slug or src.stem or src.name)
    dst = deployment_dir(site_slug)
    previous = load_manifest(site_slug) or {}
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        _copy_dir(src, dst)
        entry_path = _entry_for_dir(dst)
    elif src.suffix.lower() in {".html", ".htm"}:
        entry_path = "index.html"
        shutil.copy2(src, dst / entry_path)
    else:
        raise ValueError("deploy_path supports a static directory or an .html file")
    source_ref = src.relative_to(REPO_ROOT).as_posix() if REPO_ROOT in src.parents else str(src)
    return save_manifest(site_slug, {"source": source_ref, "entry_path": entry_path, "updated_at": now_iso(), "created_at": previous.get("created_at") or now_iso()})


def deploy_from_files(files: dict[str, str], *, slug: str, entry_path: str = "index.html") -> dict:
    if not files:
        raise ValueError("files payload is required")
    site_slug = normalize_slug(slug)
    dst = deployment_dir(site_slug)
    previous = load_manifest(site_slug) or {}
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        rel = Path(str(relative_path or "").strip())
        if not rel.name or rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"invalid deployment file path: {relative_path}")
        path = dst / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")
    if not (dst / entry_path).exists():
        raise ValueError(f"entry_path not found after deploy: {entry_path}")
    return save_manifest(site_slug, {"source": "[inline files]", "entry_path": entry_path, "updated_at": now_iso(), "created_at": previous.get("created_at") or now_iso()})
