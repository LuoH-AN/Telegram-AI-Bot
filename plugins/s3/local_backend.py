"""Local filesystem-backed encrypted storage for the S3 engine."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

from .engine import S3Backend

logger = logging.getLogger(__name__)

# Storage root
_LOCAL_DIR = Path(os.getenv("S3_LOCAL_DIR", "runtime/s3_data")).expanduser().resolve()
_ENC_KEY_ENV = "S3_LOCAL_ENCRYPTION_KEY"


def _build_cipher(key: str):
    """Build AES-256-GCM cipher from a key string."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:
        logger.warning("cryptography unavailable for local S3: %s", exc)
        return None, None

    raw = key.strip()
    if raw.startswith("base64:"):
        try:
            key_bytes = base64.urlsafe_b64decode(raw[len("base64:"):].encode("utf-8"))
        except Exception:
            key_bytes = hashlib.sha256(raw.encode("utf-8")).digest()
    elif len(raw) in {22, 24, 43, 44, 64}:
        try:
            key_bytes = base64.urlsafe_b64decode(raw.encode("utf-8"))
        except Exception:
            key_bytes = hashlib.sha256(raw.encode("utf-8")).digest()
    else:
        key_bytes = hashlib.sha256(raw.encode("utf-8")).digest()

    if len(key_bytes) not in {16, 24, 32}:
        key_bytes = hashlib.sha256(key_bytes).digest()
    key_bytes = key_bytes[:32]
    return AESGCM(key_bytes), key_bytes


def _aad(user_id: int, storage_path: str) -> bytes:
    return f"local-s3:{int(user_id)}:{storage_path}".encode("utf-8")


def _encrypt_payload(data: bytes, cipher, aad_bytes: bytes) -> bytes | None:
    if cipher is None:
        return None
    try:
        nonce = os.urandom(12)
        ciphertext = cipher.encrypt(nonce, data, aad_bytes)
        envelope = {
            "v": 1,
            "alg": "AES-256-GCM",
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        }
        return json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    except Exception as exc:
        logger.warning("encryption failed: %s", exc)
        return None


def _decrypt_payload(payload: bytes, cipher, aad_bytes: bytes) -> bytes | None:
    if cipher is None:
        return None
    if not payload.startswith(b"{"):
        return None
    try:
        envelope = json.loads(payload.decode("utf-8"))
        nonce = base64.urlsafe_b64decode(envelope["nonce"].encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(envelope["ciphertext"].encode("ascii"))
        return cipher.decrypt(nonce, ciphertext, aad_bytes)
    except Exception as exc:
        logger.debug("decryption failed: %s", exc)
        return None


class LocalS3Backend(S3Backend):
    """S3Backend that stores data on the local filesystem with AES-256-GCM encryption.

    Directory layout:
        <S3_LOCAL_DIR>/
            <user_id>/
                index.json          # encrypted S3 state (buckets + objects index)
                objects/
                    <bucket>/
                        <key_hash>  # encrypted binary blobs
    """

    def __init__(self):
        self._root = _LOCAL_DIR
        self._cipher, self._key = _build_cipher(os.getenv(_ENC_KEY_ENV) or "")
        if self._cipher is None:
            logger.debug("Local S3 backend: encryption disabled (no valid key)")
        self._root.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, user_id: int) -> Path:
        return self._root / str(int(user_id))

    def _objects_dir(self, user_id: int) -> Path:
        d = self._user_dir(user_id) / "objects"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _index_path(self, user_id: int) -> Path:
        return self._user_dir(user_id) / "index.json"

    def _object_path(self, user_id: int, bucket: str, key_hash: str) -> Path:
        bucket_dir = self._objects_dir(user_id) / bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        return bucket_dir / key_hash

    def _hash_key(self, bucket: str, key: str) -> str:
        return hashlib.sha256(f"{bucket}:{key}".encode("utf-8")).hexdigest()[:32]

    @property
    def enabled(self) -> bool:
        return True  # Always enabled (encryption is optional but we log warnings)

    @property
    def encryption_available(self) -> bool:
        return self._cipher is not None

    def _encrypt(self, data: bytes, user_id: int, bucket: str, key: str) -> bytes | None:
        if self._cipher is None:
            return data  # Fall back to plaintext
        return _encrypt_payload(data, self._cipher, _aad(user_id, f"{bucket}/{key}"))

    def _decrypt(self, data: bytes, user_id: int, bucket: str, key: str) -> bytes | None:
        if self._cipher is None:
            return data
        # Try encrypted first, fall back to plaintext
        result = _decrypt_payload(data, self._cipher, _aad(user_id, f"{bucket}/{key}"))
        if result is not None:
            return result
        # Plaintext fallback for backwards compat
        try:
            json.loads(data.decode("utf-8"))
            logger.debug("Local S3: storing plaintext object %s/%s (no encryption key)", bucket, key)
            return data
        except Exception:
            return None

    def put_object(self, user_id: int, storage_path: str, data: bytes, *, encrypt: bool) -> bool:
        # storage_path = bucket/content_hash
        parts = str(storage_path).split("/", 1)
        if len(parts) != 2:
            logger.warning("Invalid storage path: %s", storage_path)
            return False
        bucket, content_hash = parts[0], parts[1]
        key = content_hash  # The storage_path IS the content hash for dedup
        obj_path = self._object_path(user_id, bucket, content_hash)

        to_store = self._encrypt(data, user_id, bucket, key) if encrypt and self._cipher else data
        if to_store is None:
            return False
        try:
            obj_path.write_bytes(to_store)
            return True
        except Exception as exc:
            logger.warning("LocalS3 put_object failed: %s", exc)
            return False

    def get_object(self, user_id: int, storage_path: str, *, allow_plaintext: bool) -> bytes | None:
        parts = str(storage_path).split("/", 1)
        if len(parts) != 2:
            return None
        bucket, content_hash = parts[0], parts[1]
        key = content_hash
        obj_path = self._object_path(user_id, bucket, content_hash)
        if not obj_path.is_file():
            return None
        try:
            data = obj_path.read_bytes()
            if self._cipher:
                decrypted = _decrypt_payload(data, self._cipher, _aad(user_id, f"{bucket}/{key}"))
                if decrypted is not None:
                    return decrypted
            if allow_plaintext:
                return data
            return None
        except Exception as exc:
            logger.warning("LocalS3 get_object failed: %s", exc)
            return None

    def delete_object(self, user_id: int, storage_path: str) -> None:
        parts = str(storage_path).split("/", 1)
        if len(parts) != 2:
            return
        bucket, content_hash = parts[0], parts[1]
        obj_path = self._object_path(user_id, bucket, content_hash)
        try:
            obj_path.unlink(missing_ok=True)
        except Exception:
            pass

    def load_state(self, user_id: int) -> dict:
        idx = self._index_path(user_id)
        if not idx.is_file():
            return {"buckets": []}
        try:
            data = idx.read_bytes()
            if self._cipher:
                decrypted = _decrypt_payload(data, self._cipher, _aad(user_id, "state"))
                if decrypted:
                    payload = json.loads(decrypted.decode("utf-8"))
                    if isinstance(payload, dict):
                        return payload
            # Plaintext fallback
            payload = json.loads(data.decode("utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {"buckets": []}

    def save_state(self, user_id: int, state: dict) -> None:
        idx = self._index_path(user_id)
        idx.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.dumps(state, separators=(",", ":")).encode("utf-8")
            if self._cipher:
                data = _encrypt_payload(data, self._cipher, _aad(user_id, "state")) or data
            idx.write_bytes(data)
        except Exception as exc:
            logger.warning("LocalS3 save_state failed: %s", exc)

    def delete_bucket(self, user_id: int, bucket_name: str) -> None:
        bucket_dir = self._objects_dir(user_id) / bucket_name
        try:
            shutil.rmtree(bucket_dir, ignore_errors=True)
        except Exception:
            pass

    def generate_url(self, user_id: int, storage_path: str, content_type: str, *, expires: int) -> str | None:
        # Local storage doesn't have a built-in URL scheme
        # Return a special marker URL that the caller can interpret
        return f"local://{user_id}/{storage_path}"

    def list_all_objects(self, user_id: int) -> list[tuple[str, str]]:
        """List all object storage paths for a user. Returns list of (storage_path, bucket)."""
        objects_dir = self._objects_dir(user_id)
        if not objects_dir.is_dir():
            return []
        results = []
        for bucket_dir in objects_dir.iterdir():
            if not bucket_dir.is_dir():
                continue
            bucket = bucket_dir.name
            for f in bucket_dir.iterdir():
                if f.is_file():
                    results.append((f"{bucket}/{f.name}", bucket))
        return results
