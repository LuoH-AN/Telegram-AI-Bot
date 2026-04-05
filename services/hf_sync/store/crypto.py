"""Encryption/decryption helpers for HF dataset storage."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os

from .constants import ENC_MAGIC, LFS_POINTER_PREFIX

logger = logging.getLogger(__name__)

def build_cipher(store) -> bool:
    if not store._enabled:
        return False
    if store._aesgcm is not None:
        return True
    with store._lock:
        if store._aesgcm is not None:
            return True
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except Exception as exc:
            if not store._missing_crypto_logged:
                store._missing_crypto_logged = True
                logger.warning("HF dataset encryption unavailable: cryptography import failed (%s).", exc)
            return False

        raw = (store.encryption_key or "").strip()
        if not raw:
            if not store._missing_crypto_logged:
                store._missing_crypto_logged = True
                logger.warning("HF dataset encryption unavailable: missing HF_DATASET_ENCRYPTION_KEY.")
            return False
        key_bytes: bytes | None = None
        if raw.startswith("base64:"):
            try:
                key_bytes = base64.urlsafe_b64decode(raw[len("base64:"):].encode("utf-8"))
            except Exception:
                key_bytes = None
        elif len(raw) in {22, 24, 43, 44, 64}:
            try:
                key_bytes = base64.urlsafe_b64decode(raw.encode("utf-8"))
            except Exception:
                key_bytes = None
        if key_bytes is None:
            key_bytes = hashlib.sha256(raw.encode("utf-8")).digest()
        if len(key_bytes) not in {16, 24, 32}:
            logger.warning("HF dataset encryption unavailable: invalid encryption key format.")
            return False

        store._aesgcm_cls = AESGCM
        store._aesgcm = AESGCM(key_bytes)
        return True


def aad(store, filename: str) -> bytes:
    return f"{store.repo_id}:{store.branch}:{store.prefix}:{filename}".encode("utf-8")


def encrypt_payload(store, data: bytes, filename: str) -> bytes | None:
    if not build_cipher(store):
        return None
    try:
        nonce = os.urandom(12)
        ciphertext = store._aesgcm.encrypt(nonce, data, aad(store, filename))
        envelope = {
            "v": 1,
            "alg": "AES-256-GCM",
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
        }
        body = json.dumps(envelope, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return ENC_MAGIC + body
    except Exception as exc:
        logger.warning("HF store encryption failed for %s: %s", filename, exc)
        return None


def decrypt_payload(store, payload: bytes, filename: str, *, allow_plaintext: bool = False) -> bytes | None:
    if not payload.startswith(ENC_MAGIC):
        if allow_plaintext:
            return payload
        if payload.startswith(LFS_POINTER_PREFIX):
            logger.warning(
                "HF store found a Git LFS/Xet pointer for %s. Materialize large files first.",
                filename,
            )
            return None
        logger.warning("HF store rejected plaintext file %s (encryption is required).", filename)
        return None
    if not build_cipher(store):
        return None
    try:
        envelope = json.loads(payload[len(ENC_MAGIC):].decode("utf-8"))
        nonce = base64.urlsafe_b64decode(str(envelope.get("nonce") or "").encode("utf-8"))
        ciphertext = base64.urlsafe_b64decode(str(envelope.get("ciphertext") or "").encode("utf-8"))
        return store._aesgcm.decrypt(nonce, ciphertext, aad(store, filename))
    except Exception as exc:
        logger.warning("HF store decryption failed for %s: %s", filename, exc)
        return None
