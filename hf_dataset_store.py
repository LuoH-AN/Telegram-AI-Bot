"""Hugging Face Dataset-backed storage helpers.

This module provides a small optional persistence layer for ephemeral runtimes
(e.g. Hugging Face Spaces without persistent disk).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import threading
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on", "y"}
_FALSY = {"0", "false", "no", "off", "n"}
_ENC_MAGIC = b"HFENC1:"


def _is_not_found_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "404" in text
        or "not found" in text
        or "entry not found" in text
        or "revision not found" in text
    )


def _clean_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip().lstrip("/")
    if not value:
        raise ValueError("path is empty")
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe path: {path!r}")
    return "/".join(parts)


class HFDatasetStore:
    """Optional object store on top of a Hugging Face dataset repo."""

    def __init__(self) -> None:
        enabled_raw = (os.getenv("HF_DATASET_ENABLED", "1") or "1").strip().lower()
        if enabled_raw in _FALSY:
            self._enabled = False
        else:
            self._enabled = True if enabled_raw in _TRUTHY or not enabled_raw else True

        self.username = (os.getenv("HF_DATASET_USERNAME", "") or "").strip()
        self.token = (os.getenv("HF_DATASET_TOKEN", "") or "").strip()
        self.dataset_name = (os.getenv("HF_DATASET_NAME", "") or "").strip()
        self.branch = (os.getenv("HF_DATASET_BRANCH", "main") or "main").strip() or "main"
        self.prefix = (os.getenv("HF_DATASET_PREFIX", "gemen_state") or "gemen_state").strip().strip("/")
        self.encryption_key = (os.getenv("HF_DATASET_ENCRYPTION_KEY", "") or "").strip()

        self.repo_id = self._build_repo_id(self.username, self.dataset_name)
        if not self.repo_id or not self.token or not self.encryption_key:
            self._enabled = False

        self._lock = threading.Lock()
        self._client_ready = False
        self._repo_ready = False
        self._missing_dependency_logged = False
        self._missing_crypto_logged = False
        self._api = None
        self._hf_hub_download = None
        self._aesgcm_cls = None
        self._aesgcm = None

    @staticmethod
    def _build_repo_id(username: str, dataset_name: str) -> str:
        if not dataset_name:
            return ""
        if "/" in dataset_name:
            return dataset_name.strip("/")
        if username:
            return f"{username}/{dataset_name}"
        return ""

    @property
    def enabled(self) -> bool:
        return self._enabled

    def status(self) -> str:
        if not self._enabled:
            if not self.token:
                return "disabled: missing HF_DATASET_TOKEN"
            if not self.dataset_name:
                return "disabled: missing HF_DATASET_NAME"
            if not self.repo_id:
                return "disabled: missing HF_DATASET_USERNAME or invalid HF_DATASET_NAME"
            if not self.encryption_key:
                return "disabled: missing HF_DATASET_ENCRYPTION_KEY"
            return "disabled"
        return f"enabled: repo={self.repo_id} branch={self.branch}"

    def _prefixed_path(self, path: str) -> str:
        clean = _clean_path(path)
        if self.prefix:
            return f"{self.prefix}/{clean}"
        return clean

    def _ensure_client(self) -> bool:
        if not self._enabled:
            return False
        if self._client_ready:
            return True

        with self._lock:
            if self._client_ready:
                return True
            try:
                from huggingface_hub import HfApi, hf_hub_download
            except Exception as exc:
                if not self._missing_dependency_logged:
                    self._missing_dependency_logged = True
                    logger.warning(
                        "HF dataset storage disabled: huggingface_hub is unavailable (%s).",
                        exc,
                    )
                self._enabled = False
                return False

            self._api = HfApi(token=self.token)
            self._hf_hub_download = hf_hub_download
            self._client_ready = True
            return True

    def _build_cipher(self) -> bool:
        if not self._enabled:
            return False
        if self._aesgcm is not None:
            return True

        with self._lock:
            if self._aesgcm is not None:
                return True

            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except Exception as exc:
                if not self._missing_crypto_logged:
                    self._missing_crypto_logged = True
                    logger.warning(
                        "HF dataset storage disabled: cryptography is unavailable (%s).",
                        exc,
                    )
                self._enabled = False
                return False

            key_bytes: bytes | None = None
            raw = self.encryption_key
            if raw.startswith("base64:"):
                try:
                    key_bytes = base64.urlsafe_b64decode(raw[len("base64:"):].encode("utf-8"))
                except Exception:
                    key_bytes = None
            else:
                # Allow either raw passphrase or urlsafe b64 key (44 chars typical).
                if len(raw) in {22, 24, 43, 44, 64}:
                    try:
                        key_bytes = base64.urlsafe_b64decode(raw.encode("utf-8"))
                    except Exception:
                        key_bytes = None
                if key_bytes is None:
                    import hashlib

                    key_bytes = hashlib.sha256(raw.encode("utf-8")).digest()

            if key_bytes is None or len(key_bytes) not in {16, 24, 32}:
                logger.warning("HF dataset storage disabled: invalid encryption key format.")
                self._enabled = False
                return False

            self._aesgcm_cls = AESGCM
            self._aesgcm = AESGCM(key_bytes)
            return True

    def _aad(self, filename: str) -> bytes:
        return f"{self.repo_id}:{self.branch}:{self.prefix}:{filename}".encode("utf-8")

    def _encrypt_payload(self, data: bytes, filename: str) -> bytes | None:
        if not self._build_cipher():
            return None
        try:
            nonce = os.urandom(12)
            ciphertext = self._aesgcm.encrypt(nonce, data, self._aad(filename))
            envelope = {
                "v": 1,
                "alg": "AES-256-GCM",
                "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
                "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            }
            return _ENC_MAGIC + json.dumps(
                envelope,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except Exception as exc:
            logger.warning("HF store encryption failed for %s: %s", filename, exc)
            return None

    def _decrypt_payload(self, payload: bytes, filename: str) -> bytes | None:
        if not payload.startswith(_ENC_MAGIC):
            logger.warning(
                "HF store rejected plaintext file %s (encryption is required).",
                filename,
            )
            return None
        if not self._build_cipher():
            return None
        try:
            envelope = json.loads(payload[len(_ENC_MAGIC):].decode("utf-8"))
            nonce = base64.urlsafe_b64decode(str(envelope.get("nonce") or "").encode("utf-8"))
            ciphertext = base64.urlsafe_b64decode(str(envelope.get("ciphertext") or "").encode("utf-8"))
            return self._aesgcm.decrypt(nonce, ciphertext, self._aad(filename))
        except Exception as exc:
            logger.warning("HF store decryption failed for %s: %s", filename, exc)
            return None

    def _ensure_repo(self) -> bool:
        if not self._ensure_client() or not self._build_cipher():
            return False
        if self._repo_ready:
            return True

        with self._lock:
            if self._repo_ready:
                return True
            try:
                self._api.create_repo(
                    repo_id=self.repo_id,
                    repo_type="dataset",
                    exist_ok=True,
                )
                self._repo_ready = True
                return True
            except Exception as exc:
                logger.warning("Failed to ensure HF dataset repo %s: %s", self.repo_id, exc)
                return False

    def get_bytes(self, path: str) -> bytes | None:
        if not self._ensure_client():
            return None

        try:
            filename = self._prefixed_path(path)
        except ValueError as exc:
            logger.warning("HF store get_bytes rejected path %r: %s", path, exc)
            return None

        try:
            local_path = self._hf_hub_download(
                repo_id=self.repo_id,
                repo_type="dataset",
                filename=filename,
                revision=self.branch,
                token=self.token,
            )
        except Exception as exc:
            if _is_not_found_error(exc):
                return None
            logger.warning("HF store get_bytes failed for %s: %s", filename, exc)
            return None

        try:
            with open(local_path, "rb") as f:
                raw = f.read()
        except Exception as exc:
            logger.warning("HF store read local cache failed for %s: %s", filename, exc)
            return None
        return self._decrypt_payload(raw, filename)

    def put_bytes(self, path: str, data: bytes, *, commit_message: str | None = None) -> bool:
        if not self._ensure_repo():
            return False

        try:
            filename = self._prefixed_path(path)
        except ValueError as exc:
            logger.warning("HF store put_bytes rejected path %r: %s", path, exc)
            return False

        encrypted = self._encrypt_payload(data, filename)
        if encrypted is None:
            return False

        payload = io.BytesIO(encrypted)
        message = (commit_message or f"Update {filename}").strip()[:120]

        try:
            self._api.upload_file(
                path_or_fileobj=payload,
                path_in_repo=filename,
                repo_id=self.repo_id,
                repo_type="dataset",
                revision=self.branch,
                commit_message=message,
            )
            return True
        except Exception as exc:
            logger.warning("HF store put_bytes failed for %s: %s", filename, exc)
            return False

    def get_json(self, path: str) -> Any | None:
        raw = self.get_bytes(path)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            logger.warning("HF store get_json parse failed for %s: %s", path, exc)
            return None

    def put_json(self, path: str, value: Any, *, commit_message: str | None = None) -> bool:
        try:
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        except Exception as exc:
            logger.warning("HF store put_json encode failed for %s: %s", path, exc)
            return False
        return self.put_bytes(path, raw, commit_message=commit_message)

    def delete(self, path: str, *, commit_message: str | None = None) -> bool:
        if not self._ensure_client():
            return False

        try:
            filename = self._prefixed_path(path)
        except ValueError as exc:
            logger.warning("HF store delete rejected path %r: %s", path, exc)
            return False

        message = (commit_message or f"Delete {filename}").strip()[:120]

        try:
            self._api.delete_file(
                path_in_repo=filename,
                repo_id=self.repo_id,
                repo_type="dataset",
                revision=self.branch,
                commit_message=message,
            )
            return True
        except Exception as exc:
            if _is_not_found_error(exc):
                return True
            logger.warning("HF store delete failed for %s: %s", filename, exc)
            return False


_store_lock = threading.Lock()
_store: HFDatasetStore | None = None


def get_hf_dataset_store() -> HFDatasetStore:
    """Return singleton HF dataset store."""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            _store = HFDatasetStore()
    return _store
