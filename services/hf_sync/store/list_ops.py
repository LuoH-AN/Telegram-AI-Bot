"""List operations for dataset-backed object storage."""

from __future__ import annotations

import os

from .git_checkout import ensure_git_checkout
from .git_common import git_local_dir
from .paths import prefixed_path


def list_paths(store, *, prefix: str = "", limit: int = 200, recursive: bool = True) -> list[dict]:
    with store._lock:
        if not ensure_git_checkout(store):
            return []
        repo_dir = git_local_dir(store)
        scoped = _scoped_prefix(store, prefix)
        if scoped is None:
            return []
        target = os.path.join(repo_dir, scoped) if scoped else (os.path.join(repo_dir, store.prefix) if store.prefix else repo_dir)
        if os.path.isfile(target):
            key = _to_user_key(store, os.path.relpath(target, repo_dir))
            return [_entry(target, key)] if key else []
        if not os.path.isdir(target):
            return []
        rows: list[dict] = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [name for name in dirs if name != ".git"]
            for file_name in files:
                abs_path = os.path.join(root, file_name)
                key = _to_user_key(store, os.path.relpath(abs_path, repo_dir))
                if key:
                    rows.append(_entry(abs_path, key))
            if not recursive:
                break
        rows.sort(key=lambda item: item["key"])
        return rows[: max(1, min(int(limit or 200), 5000))]


def head_path(store, path: str) -> dict | None:
    with store._lock:
        if not ensure_git_checkout(store):
            return None
        try:
            scoped = prefixed_path(store, path)
        except ValueError:
            return None
        repo_dir = git_local_dir(store)
        abs_path = os.path.join(repo_dir, scoped)
        if not os.path.isfile(abs_path):
            return None
        key = _to_user_key(store, scoped)
        return _entry(abs_path, key) if key else None


def exists_path(store, path: str) -> bool:
    return head_path(store, path) is not None


def _scoped_prefix(store, prefix: str) -> str | None:
    text = (prefix or "").strip().lstrip("/")
    if not text:
        return store.prefix
    try:
        return prefixed_path(store, text)
    except ValueError:
        return None


def _to_user_key(store, rel_path: str) -> str:
    rel = str(rel_path or "").replace("\\", "/")
    if not rel:
        return ""
    if not store.prefix:
        return rel
    pref = f"{store.prefix}/"
    return rel[len(pref) :] if rel.startswith(pref) else ""


def _entry(abs_path: str, key: str) -> dict:
    stat = os.stat(abs_path)
    return {"key": key, "size": int(stat.st_size), "mtime": int(stat.st_mtime)}
