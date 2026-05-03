"""Delete operation for dataset-backed objects."""

from __future__ import annotations

import os
import shutil

from .git.checkout import ensure_git_checkout
from .git.commit import commit_git_change
from .git.common import git_local_dir, run_git
from .path import prefixed_path


def delete_path(store, path: str, *, commit_message: str | None = None) -> bool:
    with store._lock:
        if not ensure_git_checkout(store):
            return False
        try:
            filename = prefixed_path(store, path)
        except ValueError as exc:
            store._logger.warning("HF store delete rejected path %r: %s", path, exc)
            return False

        message = (commit_message or f"Delete {filename}").strip()[:120]
        repo_dir = git_local_dir(store)
        abs_path = os.path.join(repo_dir, filename)
        try:
            if os.path.lexists(abs_path):
                if os.path.isdir(abs_path) and not os.path.islink(abs_path):
                    shutil.rmtree(abs_path)
                else:
                    os.remove(abs_path)
            run_git(store, ["add", "-A", "--", "."], cwd=repo_dir)
            return commit_git_change(store, filename, message)
        except Exception as exc:
            store._logger.warning("HF store delete failed for %s: %s", filename, exc)
            return False


def delete_prefix(store, prefix: str, *, commit_message: str | None = None) -> dict:
    with store._lock:
        if not ensure_git_checkout(store):
            return {"ok": False, "deleted": 0}
        repo_dir = git_local_dir(store)
        rel_prefix = _resolve_prefix(store, prefix)
        if rel_prefix is None:
            return {"ok": False, "deleted": 0}

        try:
            deleted = _remove_prefix(repo_dir, rel_prefix)
            if deleted <= 0:
                return {"ok": True, "deleted": 0}
            message = (commit_message or f"Delete prefix: {rel_prefix or '/'}").strip()[:120]
            run_git(store, ["add", "-A", "--", "."], cwd=repo_dir)
            ok = commit_git_change(store, ".", message)
            return {"ok": bool(ok), "deleted": int(deleted)}
        except Exception as exc:
            store._logger.warning("HF store delete_prefix failed for %r: %s", prefix, exc)
            return {"ok": False, "deleted": 0}


def _resolve_prefix(store, prefix: str) -> str | None:
    raw = (prefix or "").strip().lstrip("/")
    if not raw:
        return store.prefix
    try:
        return prefixed_path(store, raw)
    except ValueError as exc:
        store._logger.warning("HF store delete_prefix rejected prefix %r: %s", prefix, exc)
        return None


def _remove_prefix(repo_dir: str, rel_prefix: str) -> int:
    if not rel_prefix:
        return _clear_repo_root(repo_dir)
    target = os.path.join(repo_dir, rel_prefix)
    if not os.path.lexists(target):
        return 0
    if os.path.isdir(target) and not os.path.islink(target):
        deleted = 0
        for root, _, files in os.walk(target):
            deleted += len(files)
        shutil.rmtree(target)
        return deleted
    os.remove(target)
    return 1


def _clear_repo_root(repo_dir: str) -> int:
    deleted = 0
    for name in os.listdir(repo_dir):
        if name == ".git":
            continue
        abs_path = os.path.join(repo_dir, name)
        if os.path.isdir(abs_path) and not os.path.islink(abs_path):
            for root, _, files in os.walk(abs_path):
                deleted += len(files)
            shutil.rmtree(abs_path)
            continue
        if os.path.exists(abs_path):
            deleted += 1
            os.remove(abs_path)
    return deleted
