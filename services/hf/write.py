"""Write/upload operations for S3-style object storage."""

from __future__ import annotations

import time

from .store import get_hf_dataset_store

from .batch import commit_object_triplet
from .index import _load_object_index
from .name import _meta_key_for_path, _normalize_object_key


def put_storage_object(
    user_id: int,
    *,
    data: bytes,
    name: str,
    filename: str | None = None,
    content_type: str = "application/octet-stream",
    encrypt: bool = False,
) -> dict:
    store = get_hf_dataset_store()
    if not store.enabled:
        return {"ok": False, "message": "S3 storage unavailable"}

    object_name = _normalize_object_key(name, default="object.dat")
    stored_filename = (filename or object_name or "object.dat").strip() or "object.dat"
    content_hash = _meta_key_for_path(object_name)
    content_path = f".hf_sync/objects/{int(user_id)}/{content_hash}" if encrypt else object_name
    meta_path = f".hf_sync/meta/{int(user_id)}/{content_hash}.json"

    created_at = time.time()
    index_path = f".hf_sync/index/{int(user_id)}.json"
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

    index = [
        item
        for item in _load_object_index(user_id)
        if str(item.get("object_name") or "") != object_name
    ]
    index.insert(0, meta)
    ok = commit_object_triplet(
        store,
        object_name=object_name,
        data=data,
        encrypt=encrypt,
        content_path=content_path,
        meta_path=meta_path,
        meta=meta,
        index_path=index_path,
        index_items=index,
    )
    if not ok:
        return {"ok": False, "message": f"Failed to store object '{object_name}'"}

    return {
        "ok": True,
        "kind": "object",
        "object_name": object_name,
        "path": object_name,
        "filename": stored_filename,
        "content_type": content_type,
        "encrypted": bool(encrypt),
        "size": len(data),
        "repo_url": store.resolve_repo_url(object_name) if not encrypt else None,
    }
