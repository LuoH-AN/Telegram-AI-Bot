"""Ensure local checkout synced to remote branch."""

from __future__ import annotations

import os
import shutil

from .constants import (
    LFS_CONCURRENT_TRANSFERS,
    LFS_TRANSFER_MAX_RETRIES,
    LFS_TRANSFER_MAX_RETRY_DELAY,
)
from .crypto import build_cipher
from .git_common import ensure_git_backend, git_local_dir, git_repo_url, run_git


def ensure_git_checkout(store) -> bool:
    if not ensure_git_backend(store) or not build_cipher(store):
        return False
    repo_dir = git_local_dir(store)
    with store._lock:
        try:
            if not os.path.isdir(os.path.join(repo_dir, ".git")):
                if os.path.exists(repo_dir):
                    shutil.rmtree(repo_dir)
                os.makedirs(os.path.dirname(repo_dir), exist_ok=True)
                run_git(
                    store,
                    ["clone", "--branch", store.branch, "--single-branch", git_repo_url(store), repo_dir],
                    network=True,
                )
                if shutil.which("git-xet"):
                    run_git(store, ["xet", "install"], cwd=repo_dir, check=False)
                run_git(store, ["config", "user.name", store.username or "gemen-bot"], cwd=repo_dir)
                email = f"{(store.username or 'gemen-bot')}@users.noreply.huggingface.co"
                run_git(store, ["config", "user.email", email], cwd=repo_dir)

            if shutil.which("git-lfs"):
                run_git(store, ["lfs", "install", "--local"], cwd=repo_dir, check=False)
                run_git(store, ["config", "lfs.concurrenttransfers", str(LFS_CONCURRENT_TRANSFERS)], cwd=repo_dir, check=False)
                run_git(store, ["config", "lfs.transfer.maxretries", str(LFS_TRANSFER_MAX_RETRIES)], cwd=repo_dir, check=False)
                run_git(store, ["config", "lfs.transfer.maxretrydelay", str(LFS_TRANSFER_MAX_RETRY_DELAY)], cwd=repo_dir, check=False)

            run_git(store, ["fetch", "origin", store.branch], cwd=repo_dir, network=True)
            run_git(store, ["checkout", store.branch], cwd=repo_dir)
            run_git(store, ["reset", "--hard", f"origin/{store.branch}"], cwd=repo_dir)
            run_git(store, ["clean", "-fd"], cwd=repo_dir)
            if shutil.which("git-lfs"):
                run_git(store, ["lfs", "pull", "origin", store.branch], cwd=repo_dir, network=True, check=False)
            return True
        except Exception as exc:
            store._logger.warning("Failed to prepare HF git checkout for %s: %s", store.repo_id, exc)
            return False
