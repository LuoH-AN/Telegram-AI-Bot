"""Byte payload operations for HF dataset store."""

from __future__ import annotations

import os

from .crypto import decrypt_payload, encrypt_payload
from .git.checkout import ensure_git_checkout
from .git.commit import commit_git_change
from .git.common import git_local_dir, run_git
from .path import prefixed_path


def get_bytes(store, path: str, *, allow_plaintext: bool = True) -> bytes | None:
    with store._lock:
        if not ensure_git_checkout(store):
            return None
        try:
            filename = prefixed_path(store, path)
        except ValueError as exc:
            store._logger.warning("HF store get_bytes rejected path %r: %s", path, exc)
            return None

        abs_path = os.path.join(git_local_dir(store), filename)
        if not os.path.isfile(abs_path):
            return None
        try:
            with open(abs_path, "rb") as handle:
                raw = handle.read()
        except Exception as exc:
            store._logger.warning("HF store read local git checkout failed for %s: %s", filename, exc)
            return None
        return decrypt_payload(store, raw, filename, allow_plaintext=allow_plaintext)


def put_bytes(
    store,
    path: str,
    data: bytes,
    *,
    commit_message: str | None = None,
    encrypt: bool = True,
) -> bool:
    with store._lock:
        if not ensure_git_checkout(store):
            return False
        try:
            filename = prefixed_path(store, path)
        except ValueError as exc:
            store._logger.warning("HF store put_bytes rejected path %r: %s", path, exc)
            return False

        payload = encrypt_payload(store, data, filename) if encrypt else data
        if payload is None:
            return False
        message = (commit_message or f"Update {filename}").strip()[:120]
        repo_dir = git_local_dir(store)
        abs_path = os.path.join(repo_dir, filename)
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "wb") as handle:
                handle.write(payload)
            run_git(store, ["add", "--all", "--", filename], cwd=repo_dir)
            return commit_git_change(store, filename, message)
        except Exception as exc:
            store._logger.warning("HF store put_bytes failed for %s: %s", filename, exc)
            return False
