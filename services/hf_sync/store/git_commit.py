"""Commit and push helpers."""

from __future__ import annotations

import os
import time

from .constants import LFS_PUSH_RETRIES, LFS_PUSH_RETRY_BACKOFF_SECONDS
from .git_common import git_local_dir, is_lfs_push_error, read_lfs_log_excerpt, run_git


def commit_git_change(store, filename: str, commit_message: str) -> bool:
    repo_dir = git_local_dir(store)
    try:
        diff = run_git(store, ["diff", "--cached", "--quiet", "--", filename], cwd=repo_dir, check=False)
        if diff.returncode == 0:
            return True
        if diff.returncode not in {0, 1}:
            raise RuntimeError(diff.stderr or diff.stdout or "git diff failed")

        run_git(store, ["commit", "-m", commit_message], cwd=repo_dir)
        error_text = ""
        for attempt in range(LFS_PUSH_RETRIES):
            push = run_git(store, ["push", "origin", f"HEAD:{store.branch}"], cwd=repo_dir, network=True, check=False)
            if push.returncode == 0:
                return True
            error_text = (push.stderr or push.stdout or "").strip()
            if not is_lfs_push_error(error_text):
                break
            if attempt < LFS_PUSH_RETRIES - 1:
                time.sleep(LFS_PUSH_RETRY_BACKOFF_SECONDS * (attempt + 1))

        file_size = _safe_size_hint(repo_dir, filename)
        if file_size is None:
            store._logger.warning("HF git push failed for %s: %s", store.repo_id, error_text)
        else:
            store._logger.warning(
                "HF git push failed for %s (file=%s size=%d bytes): %s",
                store.repo_id,
                filename,
                file_size,
                error_text,
            )
        excerpt = read_lfs_log_excerpt(repo_dir)
        if excerpt:
            store._logger.warning("HF git-lfs log excerpt for %s:\n%s", store.repo_id, excerpt)
        return False
    except Exception as exc:
        store._logger.warning("HF git commit/push failed for %s: %s", store.repo_id, exc)
        return False


def _safe_size_hint(repo_dir: str, filename: str) -> int | None:
    try:
        return os.path.getsize(os.path.join(repo_dir, filename))
    except OSError:
        return None
