"""Delete operation for dataset-backed objects."""

from __future__ import annotations

import os
import shutil

from .git_checkout import ensure_git_checkout
from .git_commit import commit_git_change
from .git_common import git_local_dir, run_git
from .paths import prefixed_path


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
