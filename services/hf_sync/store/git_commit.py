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
                store._last_sync_at = time.monotonic()
                _maybe_compact_history(store, repo_dir, commit_message)
                return True
            error_text = (push.stderr or push.stdout or "").strip()
            if not is_lfs_push_error(error_text):
                break
            if attempt < LFS_PUSH_RETRIES - 1:
                time.sleep(LFS_PUSH_RETRY_BACKOFF_SECONDS * (attempt + 1))

        if is_lfs_push_error(error_text) and _upload_via_hf_api(store, repo_dir, filename, commit_message):
            store._last_sync_at = time.monotonic()
            return True

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


def _maybe_compact_history(store, repo_dir: str, commit_message: str) -> None:
    if not bool(getattr(store, "compact_after_write", False)):
        return
    try:
        tree = (run_git(store, ["rev-parse", "HEAD^{tree}"], cwd=repo_dir).stdout or "").strip()
        if not tree:
            return
        snapshot_message = f"snapshot: {commit_message}".strip()[:120]
        created = run_git(store, ["commit-tree", tree, "-m", snapshot_message], cwd=repo_dir)
        commit_id = (created.stdout or "").strip()
        if not commit_id:
            return
        force_push = run_git(
            store,
            ["push", "--force", "origin", f"{commit_id}:{store.branch}"],
            cwd=repo_dir,
            network=True,
            check=False,
        )
        if force_push.returncode != 0:
            error_text = (force_push.stderr or force_push.stdout or "").strip()
            store._logger.warning("HF history compact failed for %s: %s", store.repo_id, error_text)
            return
        run_git(store, ["reset", "--hard", commit_id], cwd=repo_dir)
        store._last_sync_at = time.monotonic()
    except Exception as exc:
        store._logger.warning("HF history compact failed for %s: %s", store.repo_id, exc)


def _safe_size_hint(repo_dir: str, filename: str) -> int | None:
    try:
        return os.path.getsize(os.path.join(repo_dir, filename))
    except OSError:
        return None


def _upload_via_hf_api(store, repo_dir: str, filename: str, commit_message: str) -> bool:
    abs_path = os.path.join(repo_dir, filename)
    if not os.path.isfile(abs_path):
        return False
    try:
        from huggingface_hub import HfApi
    except Exception as exc:
        store._logger.warning("HF API fallback unavailable for %s: %s", store.repo_id, exc)
        return False
    try:
        api = HfApi(token=store.token)
        api.upload_file(
            path_or_fileobj=abs_path,
            path_in_repo=filename,
            repo_id=store.repo_id,
            repo_type="dataset",
            revision=store.branch,
            commit_message=commit_message,
        )
        store._logger.info("HF API upload fallback succeeded for %s (file=%s)", store.repo_id, filename)
        return True
    except Exception as exc:
        store._logger.warning("HF API upload fallback failed for %s (file=%s): %s", store.repo_id, filename, exc)
        return False
