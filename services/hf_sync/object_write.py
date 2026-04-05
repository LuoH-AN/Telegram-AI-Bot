"""Write/upload operations for HF object storage."""

from __future__ import annotations

import time

from .store import get_hf_dataset_store

from .artifact import _artifact_view_url
from .index_store import _load_object_index, _save_object_index
from .models import ObjectRecord
from .naming import _meta_key_for_path, _normalize_object_key


def put_storage_object(
    user_id: int,
    *,
    data: bytes,
    name: str,
    filename: str | None = None,
    content_type: str = "application/octet-stream",
    encrypt: bool = True,
) -> dict:
    store = get_hf_dataset_store()
    if not store.enabled:
        return {"ok": False, "message": "HF storage unavailable"}

    object_name = _normalize_object_key(name, default="object.dat")
    stored_filename = (filename or object_name or "object.dat").strip() or "object.dat"
    content_path = object_name
    meta_path = f".hf_sync/meta/{int(user_id)}/{_meta_key_for_path(content_path)}.json"

    created_at = time.time()
    meta = {
        "object_name": object_name,
        "content_path": content_path,
        "meta_path": meta_path,
        "content_type": content_type,
        "filename": stored_filename,
        "encrypted": bool(encrypt),
        "size": len(data),
        "created_at": created_at,
    }

    ok = store.put_bytes(
        content_path,
        data,
        commit_message=f"put object: {content_path}",
        encrypt=encrypt,
    ) and store.put_json(
        meta_path,
        meta,
        commit_message=f"put object meta: {content_path}",
        encrypt=False,
    )
    if not ok:
        return {"ok": False, "message": f"Failed to store object '{content_path}'"}

    index = [
        item
        for item in _load_object_index(user_id)
        if str(item.get("object_name") or "") != content_path
    ]
    index.insert(0, meta)
    _save_object_index(user_id, index)

    record = ObjectRecord(
        object_name=content_path,
        content_path=content_path,
        meta_path=meta_path,
        content_type=content_type,
        filename=stored_filename,
        encrypted=bool(encrypt),
        size=len(data),
        created_at=created_at,
    )
    return {
        "ok": True,
        "kind": "object",
        "object_name": content_path,
        "path": content_path,
        "filename": stored_filename,
        "content_type": content_type,
        "encrypted": bool(encrypt),
        "size": len(data),
        "view_url": _artifact_view_url(record, user_id=user_id),
        "repo_url": store.resolve_repo_url(content_path) if not encrypt else None,
    }
