"""HuggingFace-backed storage for the S3 engine."""

from __future__ import annotations

import logging
import os
import time
import urllib.parse

from .engine import S3Backend

logger = logging.getLogger(__name__)

# Storage root inside the HF dataset repo
_S3_ROOT = ".s3"


class HFS3Backend(S3Backend):
    """S3Backend backed by the existing HF dataset store infrastructure."""

    def __init__(self):
        self._store = _get_hf_store()
        self._state_path = f"{_S3_ROOT}/state"

    @property
    def enabled(self) -> bool:
        return self._store is not None and self._store.enabled

    def _object_path(self, user_id: int, storage_path: str) -> str:
        safe = str(storage_path).replace("../", "").lstrip("/")
        return f"{_S3_ROOT}/users/{int(user_id)}/objects/{safe}"

    def _state_path_for(self, user_id: int) -> str:
        return f"{_S3_ROOT}/users/{int(user_id)}/state.json"

    def put_object(self, user_id: int, storage_path: str, data: bytes, *, encrypt: bool) -> bool:
        if not self.enabled:
            logger.warning("HF S3 backend disabled, cannot put object")
            return False
        path = self._object_path(user_id, storage_path)
        ok = self._store.put_bytes(path, data, commit_message=f"s3: put {storage_path}", encrypt=encrypt)
        if not ok:
            logger.warning("HF store put_bytes failed for %s", path)
        return ok

    def get_object(self, user_id: int, storage_path: str, *, allow_plaintext: bool) -> bytes | None:
        if not self.enabled:
            return None
        path = self._object_path(user_id, storage_path)
        return self._store.get_bytes(path, allow_plaintext=allow_plaintext)

    def delete_object(self, user_id: int, storage_path: str) -> None:
        if not self.enabled:
            return
        path = self._object_path(user_id, storage_path)
        try:
            self._store.delete(path, commit_message=f"s3: delete {storage_path}")
        except Exception:
            logger.debug("delete_object %s failed (may not exist)", path)

    def load_state(self, user_id: int) -> dict:
        if not self.enabled:
            return {"buckets": []}
        path = self._state_path_for(user_id)
        payload = self._store.get_json(path, allow_plaintext=True)
        if payload and isinstance(payload, dict):
            return payload
        return {"buckets": []}

    def save_state(self, user_id: int, state: dict) -> None:
        if not self.enabled:
            return
        path = self._state_path_for(user_id)
        try:
            self._store.put_json(path, state, commit_message="s3: save state", encrypt=False)
        except Exception:
            logger.warning("HF store save_state failed for user %d", user_id)

    def delete_bucket(self, user_id: int, bucket_name: str) -> None:
        """Delete all objects belonging to a bucket by prefix."""
        if not self.enabled:
            return
        prefix = f"{_S3_ROOT}/users/{int(user_id)}/objects/{bucket_name}/"
        try:
            self._store.delete_prefix(prefix, commit_message=f"s3: delete bucket {bucket_name}")
        except Exception:
            logger.debug("delete_bucket %s failed", bucket_name)

    def generate_url(self, user_id: int, storage_path: str, content_type: str, *, expires: int) -> str | None:
        """Generate a HuggingFace CDN URL for the object.

        Returns a URL that expires in `expires` seconds. The URL points to
        the HuggingFace dataset blob, which is publicly accessible.
        """
        if not self.enabled:
            return None

        repo_id = self._store.repo_id
        if not repo_id:
            return None

        # Build a URL-based artifact token path
        # The web/app.py artifact route at /artifacts/{token} serves from the HF store
        # We construct a token payload that the artifact route can decode
        import base64
        import json
        import time

        payload = {
            "path": self._object_path(user_id, storage_path),
            "content_type": content_type,
            "encrypted": True,
            "exp": int(time.time()) + expires,
            "size": 0,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
        # Remove padding to make URL-safe
        encoded = encoded.rstrip("=")
        return f"/artifacts/{encoded}"


_s3_store: HFS3Backend | None = None


def _get_hf_store():
    """Lazily import the HF store to avoid circular imports."""
    try:
        from services.hf.store import get_hf_dataset_store
        return get_hf_dataset_store()
    except Exception:
        logger.warning("HF dataset store unavailable, S3 backend disabled")
        return None


def get_s3_backend() -> HFS3Backend:
    global _s3_store
    if _s3_store is None:
        _s3_store = HFS3Backend()
    return _s3_store
