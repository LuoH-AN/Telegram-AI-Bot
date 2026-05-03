"""Batch write helpers for single-commit object uploads."""

from __future__ import annotations

import json
import os

from .store.crypto import encrypt_payload
from .store.git.checkout import ensure_git_checkout
from .store.git.commit import commit_git_change
from .store.git.common import git_local_dir, run_git
from .store.path import prefixed_path


def commit_object_triplet(store, *, object_name: str, data: bytes, encrypt: bool, content_path: str, meta_path: str, meta: dict, index_path: str, index_items: list[dict]) -> bool:
    with store._lock:
        if not ensure_git_checkout(store):
            return False
        repo_dir = git_local_dir(store)
        payload = encrypt_payload(store, data, content_path) if encrypt else data
        if payload is None:
            return False
        try:
            content_file = prefixed_path(store, content_path)
            meta_file = prefixed_path(store, meta_path)
            index_file = prefixed_path(store, index_path)
            for rel, raw in (
                (content_file, payload),
                (meta_file, json.dumps(meta, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")),
                (index_file, json.dumps(index_items, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            ):
                abs_path = os.path.join(repo_dir, rel)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "wb") as handle:
                    handle.write(raw)
            run_git(store, ["add", "--all", "--", content_file, meta_file, index_file], cwd=repo_dir)
            return commit_git_change(store, content_file, f"put object: {object_name}")
        except Exception as exc:
            store._logger.warning("HF store batch write failed for %s: %s", object_name, exc)
            return False
