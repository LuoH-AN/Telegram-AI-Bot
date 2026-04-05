"""Delete operations for S3-style object storage."""

from __future__ import annotations

from .store import get_hf_dataset_store

from .index_store import _load_object_index, _save_object_index
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

    ok = store.delete(
        str(match.get("content_path") or ""),
        commit_message=f"delete object: {object_name}",
    )
    meta_path = str(match.get("meta_path") or "")
    if meta_path:
        ok = store.delete(
            meta_path,
            commit_message=f"delete object meta: {object_name}",
        ) and ok
    if ok:
        _save_object_index(
            user_id,
            [
                item
                for item in index
                if str(item.get("object_name") or "") != object_name
            ],
        )
    return ok
