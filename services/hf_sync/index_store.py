"""Object index persistence helpers."""

from __future__ import annotations

from .store import get_hf_dataset_store

from .naming import _object_index_path


def _load_object_index(user_id: int) -> list[dict]:
    store = get_hf_dataset_store()
    if not store.enabled:
        return []
    payload = store.get_json(_object_index_path(user_id), allow_plaintext=True)
    return payload if isinstance(payload, list) else []


def _save_object_index(user_id: int, items: list[dict]) -> bool:
    store = get_hf_dataset_store()
    if not store.enabled:
        return False
    return store.put_json(
        _object_index_path(user_id),
        items,
        commit_message=f"update object index: {user_id}",
        encrypt=False,
    )
