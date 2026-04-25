"""URL resolution branch for hf_sync commands."""

from __future__ import annotations

import json

from .store import get_hf_dataset_store

from .record import ObjectRecord
from .object import _artifact_view_url


def resolve_url_output(user_id: int, object_key: str, items: list[dict]) -> tuple[bool, str]:
    store = get_hf_dataset_store()
    match = next(
        (item for item in items if str(item.get("object_name") or "") == object_key),
        None,
    )
    if match is None:
        repo_url = store.resolve_repo_url(object_key)
        if not repo_url:
            return False, f"Object '{object_key}' not found."
        return True, json.dumps({"repo_url": repo_url, "view_url": None}, ensure_ascii=False, indent=2)

    record = ObjectRecord(
        object_name=str(match["object_name"]),
        content_path=str(match["content_path"]),
        meta_path=str(match["meta_path"]),
        content_type=str(match["content_type"]),
        filename=str(match["filename"]),
        encrypted=bool(match["encrypted"]),
        size=int(match["size"]),
        created_at=float(match["created_at"]),
    )
    payload = {
        "view_url": _artifact_view_url(record, user_id=user_id),
        "repo_url": (
            store.resolve_repo_url(record.content_path)
            if not record.encrypted
            else None
        ),
    }
    return True, json.dumps(payload, ensure_ascii=False, indent=2)
