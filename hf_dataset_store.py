"""Hugging Face Dataset-backed storage helpers.

This module provides a small optional persistence layer for ephemeral runtimes
(e.g. Hugging Face Spaces without persistent disk).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import tempfile
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on", "y"}
_FALSY = {"0", "false", "no", "off", "n"}
_ENC_MAGIC = b"HFENC1:"


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

        self._lock = threading.RLock()
        self._missing_crypto_logged = False
        self._aesgcm_cls = None
        self._aesgcm = None
        self._git_repo_dir: str | None = None

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
        return f"enabled: repo={self.repo_id} branch={self.branch} backend=git"

    def _prefixed_path(self, path: str) -> str:
        clean = _clean_path(path)
        if self.prefix:
            return f"{self.prefix}/{clean}"
        return clean

    def _ensure_git_backend(self) -> bool:
        if not self._enabled:
            return False
        if not shutil.which("git"):
            logger.warning("HF dataset storage disabled: git is unavailable.")
            self._enabled = False
            return False
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

    def _git_repo_url(self) -> str:
        return f"https://huggingface.co/datasets/{self.repo_id}"

    def _git_local_dir(self) -> str:
        if self._git_repo_dir:
            return self._git_repo_dir
        digest = hashlib.sha256(f"{self.repo_id}:{self.branch}".encode("utf-8")).hexdigest()[:16]
        path = os.path.join(tempfile.gettempdir(), "gemen_hf_git", digest)
        self._git_repo_dir = path
        return path

    def _git_auth_header(self) -> str:
        username = self.username or "__token__"
        token = self.token
        basic = base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("ascii")
        return f"AUTHORIZATION: Basic {basic}"

    def _run_git(
        self,
        args: list[str],
        *,
        cwd: str | None = None,
        network: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        cmd = ["git"]
        if network:
            cmd.extend(["-c", f"http.extraHeader={self._git_auth_header()}"])
        cmd.extend(args)
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if check and result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
        return result

    def _ensure_git_checkout(self) -> bool:
        if not self._ensure_git_backend() or not self._build_cipher():
            return False

        repo_dir = self._git_local_dir()
        with self._lock:
            git_dir = os.path.join(repo_dir, ".git")
            try:
                if not os.path.isdir(git_dir):
                    if os.path.exists(repo_dir):
                        shutil.rmtree(repo_dir)
                    os.makedirs(os.path.dirname(repo_dir), exist_ok=True)
                    self._run_git(
                        [
                            "clone",
                            "--branch",
                            self.branch,
                            "--single-branch",
                            self._git_repo_url(),
                            repo_dir,
                        ],
                        network=True,
                    )
                    if shutil.which("git-xet"):
                        try:
                            self._run_git(["xet", "install"], cwd=repo_dir, check=False)
                        except Exception:
                            pass
                    self._run_git(["config", "user.name", self.username or "gemen-bot"], cwd=repo_dir)
                    self._run_git(
                        [
                            "config",
                            "user.email",
                            f"{(self.username or 'gemen-bot')}@users.noreply.huggingface.co",
                        ],
                        cwd=repo_dir,
                    )

                self._run_git(["fetch", "origin", self.branch], cwd=repo_dir, network=True)
                self._run_git(["checkout", self.branch], cwd=repo_dir)
                self._run_git(["reset", "--hard", f"origin/{self.branch}"], cwd=repo_dir)
                self._run_git(["clean", "-fd"], cwd=repo_dir)
                return True
            except Exception as exc:
                logger.warning(
                    "Failed to prepare HF git checkout for %s: %s. "
                    "Make sure the dataset repo already exists and the token has write access.",
                    self.repo_id,
                    exc,
                )
                return False

    def _commit_git_change(self, filename: str, commit_message: str) -> bool:
        repo_dir = self._git_local_dir()
        try:
            diff = self._run_git(["diff", "--cached", "--quiet", "--", filename], cwd=repo_dir, check=False)
            if diff.returncode == 0:
                return True
            if diff.returncode not in {0, 1}:
                raise RuntimeError(diff.stderr or diff.stdout or "git diff failed")

            self._run_git(["commit", "-m", commit_message], cwd=repo_dir)
            push = self._run_git(["push", "origin", f"HEAD:{self.branch}"], cwd=repo_dir, network=True, check=False)
            if push.returncode == 0:
                return True

            logger.warning("HF git push failed for %s: %s", self.repo_id, (push.stderr or push.stdout or "").strip())
            return False
        except Exception as exc:
            logger.warning("HF git commit/push failed for %s: %s", self.repo_id, exc)
            return False

    def get_bytes(self, path: str) -> bytes | None:
        with self._lock:
            if not self._ensure_git_checkout():
                return None

            try:
                filename = self._prefixed_path(path)
            except ValueError as exc:
                logger.warning("HF store get_bytes rejected path %r: %s", path, exc)
                return None

            abs_path = os.path.join(self._git_local_dir(), filename)
            if not os.path.isfile(abs_path):
                return None

            try:
                with open(abs_path, "rb") as f:
                    raw = f.read()
            except Exception as exc:
                logger.warning("HF store read local git checkout failed for %s: %s", filename, exc)
                return None
            return self._decrypt_payload(raw, filename)

    def put_bytes(self, path: str, data: bytes, *, commit_message: str | None = None) -> bool:
        with self._lock:
            if not self._ensure_git_checkout():
                return False

            try:
                filename = self._prefixed_path(path)
            except ValueError as exc:
                logger.warning("HF store put_bytes rejected path %r: %s", path, exc)
                return False

            encrypted = self._encrypt_payload(data, filename)
            if encrypted is None:
                return False

            message = (commit_message or f"Update {filename}").strip()[:120]
            repo_dir = self._git_local_dir()
            abs_path = os.path.join(repo_dir, filename)

            try:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "wb") as f:
                    f.write(encrypted)
                self._run_git(["add", "--all", "--", filename], cwd=repo_dir)
                return self._commit_git_change(filename, message)
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
        with self._lock:
            if not self._ensure_git_checkout():
                return False

            try:
                filename = self._prefixed_path(path)
            except ValueError as exc:
                logger.warning("HF store delete rejected path %r: %s", path, exc)
                return False

            message = (commit_message or f"Delete {filename}").strip()[:120]
            repo_dir = self._git_local_dir()
            abs_path = os.path.join(repo_dir, filename)

            try:
                if os.path.lexists(abs_path):
                    if os.path.isdir(abs_path) and not os.path.islink(abs_path):
                        shutil.rmtree(abs_path)
                    else:
                        os.remove(abs_path)
                self._run_git(["add", "--all", "--", filename], cwd=repo_dir)
                return self._commit_git_change(filename, message)
            except Exception as exc:
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
