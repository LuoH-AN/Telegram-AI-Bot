"""Delete operations for S3-style object storage."""

from __future__ import annotations

import json
import os

from .store import get_hf_dataset_store
from .store.git_checkout import ensure_git_checkout
from .store.git_commit import commit_git_change
from .store.git_common import git_local_dir, run_git
from .store.paths import prefixed_path

from .index_store import _load_object_index
from .naming import _normalize_object_key


def delete_storage_object(user_id: int, *, name: str) -> bool:
    store = get_hf_dataset_store()
    if not store.enabled:
        return False

    object_name = _normalize_object_key(name, default="object.dat")
    index = _load_object_index(user_id)
    match = next(
        (item for item in index if str(item.get("object_name") or "") == object_name),
        None,
    )
    if not match:
        return False

    remaining = [
        item
        for item in index
        if str(item.get("object_name") or "") != object_name
    ]
    index_path = f".hf_sync/index/{int(user_id)}.json"
    content_path = str(match.get("content_path") or "")
    meta_path = str(match.get("meta_path") or "")

    with store._lock:
        if not ensure_git_checkout(store):
            return False
        repo_dir = git_local_dir(store)
        try:
            paths = [content_path, meta_path, index_path]
            rel_paths: list[str] = []
            for path in paths:
                if not path:
                    continue
                rel = prefixed_path(store, path)
                rel_paths.append(rel)
                abs_path = os.path.join(repo_dir, rel)
                if os.path.isfile(abs_path):
                    os.remove(abs_path)

            index_rel = prefixed_path(store, index_path)
            index_abs = os.path.join(repo_dir, index_rel)
            os.makedirs(os.path.dirname(index_abs), exist_ok=True)
            with open(index_abs, "wb") as handle:
                handle.write(json.dumps(remaining, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
            if index_rel not in rel_paths:
                rel_paths.append(index_rel)

            run_git(store, ["add", "--all", "--", *rel_paths], cwd=repo_dir)
            return commit_git_change(store, index_rel, f"delete object: {object_name}")
        except Exception as exc:
            store._logger.warning("HF object delete failed for %s: %s", object_name, exc)
            return False
