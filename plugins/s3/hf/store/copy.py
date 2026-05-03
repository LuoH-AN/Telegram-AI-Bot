"""Copy and move operations for dataset-backed object storage."""

from __future__ import annotations

import os
import shutil

from .git.checkout import ensure_git_checkout
from .git.commit import commit_git_change
from .git.common import git_local_dir, run_git
from .path import prefixed_path


def copy_path(
    store,
    src_path: str,
    dst_path: str,
    *,
    overwrite: bool = True,
    commit_message: str | None = None,
) -> bool:
    with store._lock:
        if not ensure_git_checkout(store):
            return False
        src_rel, dst_rel = _resolve_paths(store, src_path, dst_path)
        if src_rel is None or dst_rel is None:
            return False
        message = (commit_message or f"Copy {src_rel} -> {dst_rel}").strip()[:120]
        repo_dir = git_local_dir(store)
        src_abs = os.path.join(repo_dir, src_rel)
        dst_abs = os.path.join(repo_dir, dst_rel)
        try:
            if not os.path.isfile(src_abs):
                return False
            if os.path.exists(dst_abs) and not overwrite:
                return False
            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            shutil.copy2(src_abs, dst_abs)
            run_git(store, ["add", "--all", "--", src_rel, dst_rel], cwd=repo_dir)
            return commit_git_change(store, dst_rel, message)
        except Exception as exc:
            store._logger.warning("HF store copy failed for %s -> %s: %s", src_rel, dst_rel, exc)
            return False


def move_path(
    store,
    src_path: str,
    dst_path: str,
    *,
    overwrite: bool = True,
    commit_message: str | None = None,
) -> bool:
    with store._lock:
        if not ensure_git_checkout(store):
            return False
        src_rel, dst_rel = _resolve_paths(store, src_path, dst_path)
        if src_rel is None or dst_rel is None:
            return False
        message = (commit_message or f"Move {src_rel} -> {dst_rel}").strip()[:120]
        repo_dir = git_local_dir(store)
        src_abs = os.path.join(repo_dir, src_rel)
        dst_abs = os.path.join(repo_dir, dst_rel)
        try:
            if not os.path.isfile(src_abs):
                return False
            if os.path.exists(dst_abs):
                if not overwrite:
                    return False
                if os.path.isdir(dst_abs) and not os.path.islink(dst_abs):
                    shutil.rmtree(dst_abs)
                else:
                    os.remove(dst_abs)
            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            shutil.move(src_abs, dst_abs)
            _cleanup_empty_parent_dirs(repo_dir, os.path.dirname(src_abs))
            run_git(store, ["add", "--all", "--", src_rel, dst_rel], cwd=repo_dir)
            return commit_git_change(store, dst_rel, message)
        except Exception as exc:
            store._logger.warning("HF store move failed for %s -> %s: %s", src_rel, dst_rel, exc)
            return False


def _resolve_paths(store, src_path: str, dst_path: str) -> tuple[str | None, str | None]:
    try:
        src_rel = prefixed_path(store, src_path)
        dst_rel = prefixed_path(store, dst_path)
    except ValueError as exc:
        store._logger.warning("HF store copy/move rejected path: %s", exc)
        return None, None
    if src_rel == dst_rel:
        return None, None
    return src_rel, dst_rel


def _cleanup_empty_parent_dirs(repo_dir: str, directory: str) -> None:
    current = directory
    while current and current != repo_dir:
        if os.path.basename(current) == ".git":
            return
        try:
            if os.listdir(current):
                return
            os.rmdir(current)
        except OSError:
            return
        current = os.path.dirname(current)
