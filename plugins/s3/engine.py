"""S3-compatible object storage engine.

Provides a clean S3-like interface (bucket + object key model) on top of
any storage backend. The default backend is HuggingFace datasets via hf_backend.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class S3Object:
    key: str
    content_type: str
    metadata: dict[str, str]
    size: int
    mtime: float
    storage_path: str
    encrypted: bool = False
    url_id: int = 0


@dataclass
class S3Bucket:
    name: str
    created_at: float
    objects: dict[str, S3Object] = field(default_factory=dict)
    next_url_id: int = 1

    def object_count(self) -> int:
        return len(self.objects)

    def total_size(self) -> int:
        return sum(obj.size for obj in self.objects.values())


class S3Service:
    """In-memory S3 engine with backend persistence.

    Manages buckets and objects for a single user (user_id). All mutations
    are immediately reflected in-memory and asynchronously persisted to the
    backend.
    """

    def __init__(self, user_id: int, backend: S3Backend):
        self._user_id = user_id
        self._backend = backend
        self._buckets: dict[str, S3Bucket] = {}
        self._dirty = False

    # ---- Bucket operations ----

    def create_bucket(self, name: str) -> dict:
        """Create a bucket. Returns dict with ok/status."""
        name = self._normalize_bucket_name(name)
        if name in self._buckets:
            return {"ok": False, "error": f"Bucket '{name}' already exists"}
        bucket = S3Bucket(name=name, created_at=time.time())
        self._buckets[name] = bucket
        self._persist()
        return {"ok": True, "bucket": name}

    def delete_bucket(self, name: str) -> dict:
        """Delete an empty bucket. Returns dict with ok/status."""
        name = self._normalize_bucket_name(name)
        bucket = self._buckets.get(name)
        if not bucket:
            return {"ok": False, "error": f"Bucket '{name}' not found"}
        if bucket.objects:
            return {"ok": False, "error": f"Bucket '{name}' is not empty ({bucket.object_count()} objects)"}
        del self._buckets[name]
        self._backend.delete_bucket(self._user_id, name)
        self._persist()
        return {"ok": True, "bucket": name}

    def list_buckets(self) -> list[dict]:
        """List all buckets with object count and total size."""
        return [
            {
                "name": b.name,
                "created_at": b.created_at,
                "object_count": b.object_count(),
                "total_size": b.total_size(),
            }
            for b in sorted(self._buckets.values(), key=lambda x: x.name)
        ]

    def head_bucket(self, name: str) -> dict | None:
        """Get bucket metadata or None if not found."""
        name = self._normalize_bucket_name(name)
        bucket = self._buckets.get(name)
        if not bucket:
            return None
        return {
            "name": bucket.name,
            "created_at": bucket.created_at,
            "object_count": bucket.object_count(),
            "total_size": bucket.total_size(),
        }

    # ---- Object operations ----

    def put_object(
        self,
        bucket_name: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        encrypt: bool = False,
    ) -> dict:
        """Store an object. Returns dict with ok/status."""
        bucket_name = self._normalize_bucket_name(bucket_name)
        key = self._normalize_object_key(key)

        if not bucket_name:
            return {"ok": False, "error": "Bucket name required"}
        if not key:
            return {"ok": False, "error": "Object key required"}
        if not data:
            return {"ok": False, "error": "Object data required"}

        bucket = self._buckets.get(bucket_name)
        if not bucket:
            return {"ok": False, "error": f"Bucket '{bucket_name}' not found. Create it first with create_bucket."}

        # Compute storage path
        content_hash = hashlib.sha256(data).hexdigest()[:32]
        storage_path = f"{bucket_name}/{content_hash}"
        mtime = time.time()

        # Persist data to backend
        ok = self._backend.put_object(self._user_id, storage_path, data, encrypt=encrypt)
        if not ok:
            return {"ok": False, "error": "Failed to persist object to storage backend"}

        # Update in-memory index
        url_id = bucket.next_url_id
        bucket.next_url_id += 1
        obj = S3Object(
            key=key,
            content_type=content_type,
            metadata=dict(metadata or {}),
            size=len(data),
            mtime=mtime,
            storage_path=storage_path,
            encrypted=encrypt,
            url_id=url_id,
        )
        bucket.objects[key] = obj
        self._persist()
        return {
            "ok": True,
            "bucket": bucket_name,
            "key": key,
            "size": len(data),
            "content_type": content_type,
            "url_id": url_id,
        }

    def get_object(self, bucket_name: str, key: str, decrypt: bool = True) -> dict:
        """Retrieve object data and metadata. Returns dict with ok/data/error."""
        bucket_name = self._normalize_bucket_name(bucket_name)
        key = self._normalize_object_key(key)
        bucket = self._buckets.get(bucket_name)
        if not bucket:
            return {"ok": False, "error": f"Bucket '{bucket_name}' not found"}
        obj = bucket.objects.get(key)
        if not obj:
            return {"ok": False, "error": f"Object '{key}' not found in bucket '{bucket_name}'"}

        data = self._backend.get_object(self._user_id, obj.storage_path, allow_plaintext=not obj.encrypted)
        if data is None:
            return {"ok": False, "error": f"Object '{key}' storage content not found"}
        return {
            "ok": True,
            "bucket": bucket_name,
            "key": key,
            "data": data,
            "content_type": obj.content_type,
            "metadata": obj.metadata,
            "size": obj.size,
        }

    def head_object(self, bucket_name: str, key: str) -> dict | None:
        """Get object metadata without data. Returns None if not found."""
        bucket_name = self._normalize_bucket_name(bucket_name)
        key = self._normalize_object_key(key)
        bucket = self._buckets.get(bucket_name)
        if not bucket:
            return None
        obj = bucket.objects.get(key)
        if not obj:
            return None
        return {
            "bucket": bucket_name,
            "key": obj.key,
            "content_type": obj.content_type,
            "metadata": obj.metadata,
            "size": obj.size,
            "mtime": obj.mtime,
            "encrypted": obj.encrypted,
        }

    def delete_object(self, bucket_name: str, key: str) -> dict:
        """Delete an object. Returns dict with ok/status."""
        bucket_name = self._normalize_bucket_name(bucket_name)
        key = self._normalize_object_key(key)
        bucket = self._buckets.get(bucket_name)
        if not bucket:
            return {"ok": False, "error": f"Bucket '{bucket_name}' not found"}
        obj = bucket.objects.pop(key, None)
        if not obj:
            return {"ok": False, "error": f"Object '{key}' not found"}
        self._backend.delete_object(self._user_id, obj.storage_path)
        self._persist()
        return {"ok": True, "bucket": bucket_name, "key": key}

    def list_objects(self, bucket_name: str, prefix: str = "", limit: int = 200) -> list[dict]:
        """List objects in a bucket with optional prefix filter."""
        bucket_name = self._normalize_bucket_name(bucket_name)
        prefix = self._normalize_object_key(prefix)
        bucket = self._buckets.get(bucket_name)
        if not bucket:
            return []
        prefix_lower = prefix.lower()
        results = []
        for key, obj in bucket.objects.items():
            if prefix and not key.lower().startswith(prefix_lower):
                continue
            results.append({
                "key": key,
                "content_type": obj.content_type,
                "metadata": obj.metadata,
                "size": obj.size,
                "mtime": obj.mtime,
            })
        results.sort(key=lambda x: x["key"])
        return results[:limit]

    def copy_object(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str, overwrite: bool = True) -> dict:
        """Copy an object within or across buckets."""
        src_bucket = self._normalize_bucket_name(src_bucket)
        dst_bucket = self._normalize_bucket_name(dst_bucket)
        src_key = self._normalize_object_key(src_key)
        dst_key = self._normalize_object_key(dst_key)
        src_b = self._buckets.get(src_bucket)
        if not src_b:
            return {"ok": False, "error": f"Source bucket '{src_bucket}' not found"}
        obj = src_b.objects.get(src_key)
        if not obj:
            return {"ok": False, "error": f"Source object '{src_key}' not found in '{src_bucket}'"}

        dst_b = self._buckets.get(dst_bucket)
        if not dst_b:
            return {"ok": False, "error": f"Destination bucket '{dst_bucket}' not found"}

        if not overwrite and dst_key in dst_b.objects:
            return {"ok": False, "error": f"Destination object '{dst_key}' already exists (overwrite=False)"}

        data = self._backend.get_object(self._user_id, obj.storage_path, allow_plaintext=not obj.encrypted)
        if data is None:
            return {"ok": False, "error": f"Failed to read source object data"}

        ok = self._backend.put_object(self._user_id, obj.storage_path, data, encrypt=obj.encrypted)
        if not ok:
            return {"ok": False, "error": "Failed to persist copy to storage backend"}

        new_obj = S3Object(
            key=dst_key,
            content_type=obj.content_type,
            metadata=dict(obj.metadata),
            size=obj.size,
            mtime=time.time(),
            storage_path=obj.storage_path,
            encrypted=obj.encrypted,
        )
        dst_b.objects[dst_key] = new_obj
        self._persist()
        return {"ok": True, "src_bucket": src_bucket, "src_key": src_key, "dst_bucket": dst_bucket, "dst_key": dst_key}

    def move_object(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str, overwrite: bool = True) -> dict:
        """Move an object within or across buckets."""
        result = self.copy_object(src_bucket, src_key, dst_bucket, dst_key, overwrite=overwrite)
        if not result.get("ok"):
            return result
        return self.delete_object(src_bucket, src_key)

    def get_url(self, bucket_name: str, key: str, expires: int = 3600) -> dict:
        """Generate a temporary access URL for an object."""
        import os
        bucket_name = self._normalize_bucket_name(bucket_name)
        key = self._normalize_object_key(key)
        bucket = self._buckets.get(bucket_name)
        if not bucket:
            return {"ok": False, "error": f"Bucket '{bucket_name}' not found"}
        obj = bucket.objects.get(key)
        if not obj:
            return {"ok": False, "error": f"Object '{key}' not found"}

        base_url = (os.getenv("WEB_BASE_URL") or "").rstrip("/")
        url_id = obj.url_id or 0
        if url_id <= 0:
            return {"ok": False, "error": "Object has no url_id"}
        url = f"{base_url}/s/{url_id}" if base_url else f"/s/{url_id}"
        return {
            "ok": True,
            "url": url,
            "url_id": url_id,
            "expires": expires,
            "bucket": bucket_name,
            "key": key,
        }

    def get_object_by_url_id(self, url_id: int) -> dict | None:
        """Find object by url_id across all buckets."""
        for bucket in self._buckets.values():
            for obj in bucket.objects.values():
                if obj.url_id == url_id:
                    return {
                        "bucket": bucket.name,
                        "key": obj.key,
                        "storage_path": obj.storage_path,
                        "content_type": obj.content_type,
                        "encrypted": obj.encrypted,
                    }
        return None

    # ---- Persistence ----

    def load(self) -> None:
        """Load state from backend into memory."""
        state = self._backend.load_state(self._user_id)
        self._buckets = {}
        for bucket_data in state.get("buckets", []):
            bucket = S3Bucket(
                name=str(bucket_data["name"]),
                created_at=float(bucket_data["created_at"]),
                objects={},
                next_url_id=int(bucket_data.get("next_url_id", 1)),
            )
            for key, obj_data in bucket_data.get("objects", {}).items():
                bucket.objects[key] = S3Object(
                    key=str(key),
                    content_type=str(obj_data.get("content_type", "application/octet-stream")),
                    metadata=dict(obj_data.get("metadata") or {}),
                    size=int(obj_data.get("size", 0)),
                    mtime=float(obj_data.get("mtime", 0)),
                    storage_path=str(obj_data["storage_path"]),
                    encrypted=bool(obj_data.get("encrypted", False)),
                    url_id=int(obj_data.get("url_id", 0)),
                )
            self._buckets[bucket.name] = bucket

    def _persist(self) -> None:
        """Persist current in-memory state to backend."""
        state = {"buckets": []}
        for bucket in self._buckets.values():
            bucket_data = {
                "name": bucket.name,
                "created_at": bucket.created_at,
                "next_url_id": bucket.next_url_id,
                "objects": {},
            }
            for key, obj in bucket.objects.items():
                bucket_data["objects"][key] = {
                    "content_type": obj.content_type,
                    "metadata": obj.metadata,
                    "size": obj.size,
                    "mtime": obj.mtime,
                    "storage_path": obj.storage_path,
                    "encrypted": obj.encrypted,
                    "url_id": obj.url_id,
                }
            state["buckets"].append(bucket_data)
        self._backend.save_state(self._user_id, state)

    # ---- Normalization helpers ----

    @staticmethod
    def _normalize_bucket_name(name: str) -> str:
        """Normalize bucket name: lowercase, no leading/trailing slashes."""
        return str(name or "").strip().lower().lstrip("/").rstrip("/")

    @staticmethod
    def _normalize_object_key(key: str) -> str:
        """Normalize object key: strip slashes."""
        return str(key or "").strip().lstrip("/").rstrip("/")


class S3Backend:
    """Abstract storage backend interface for S3Service."""

    def put_object(self, user_id: int, storage_path: str, data: bytes, *, encrypt: bool) -> bool:
        """Persist object data. Return True on success."""
        raise NotImplementedError

    def get_object(self, user_id: int, storage_path: str, *, allow_plaintext: bool) -> bytes | None:
        """Retrieve object data. Return None if not found."""
        raise NotImplementedError

    def delete_object(self, user_id: int, storage_path: str) -> None:
        """Delete object data."""
        raise NotImplementedError

    def load_state(self, user_id: int) -> dict:
        """Load S3 engine state (buckets + objects index)."""
        raise NotImplementedError

    def save_state(self, user_id: int, state: dict) -> None:
        """Persist S3 engine state."""
        raise NotImplementedError

    def delete_bucket(self, user_id: int, bucket_name: str) -> None:
        """Delete all data for a bucket."""
        raise NotImplementedError

    def generate_url(self, user_id: int, storage_path: str, content_type: str, *, expires: int) -> str | None:
        """Generate a temporary access URL. Return None if not supported."""
        return None

    @property
    def enabled(self) -> bool:
        """Whether the backend is available."""
        return True
