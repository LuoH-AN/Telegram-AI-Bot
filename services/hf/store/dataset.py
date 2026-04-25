"""Store facade used by the HF object service."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from .bytes import get_bytes, put_bytes
from .config import FALSY, TRUTHY
from .copy import copy_path, move_path
from .delete import delete_path, delete_prefix
from .json import get_json, put_json, resolve_repo_url
from .list import exists_path, head_path, list_paths
from .path import build_repo_id

logger = logging.getLogger(__name__)


class HFDatasetStore:
    """Optional object store on top of a Hugging Face dataset repo."""

    def __init__(self) -> None:
        enabled_raw = (os.getenv("HF_DATASET_ENABLED", "1") or "1").strip().lower()
        self._enabled = False if enabled_raw in FALSY else (enabled_raw in TRUTHY or not enabled_raw)
        self.username = (os.getenv("HF_DATASET_USERNAME", "") or "").strip()
        self.token = (os.getenv("HF_DATASET_TOKEN", "") or "").strip()
        self.dataset_name = (os.getenv("HF_DATASET_NAME", "") or "").strip()
        self.branch = (os.getenv("HF_DATASET_BRANCH", "main") or "main").strip() or "main"
        self.prefix = (os.getenv("HF_DATASET_PREFIX", "") or "").strip().strip("/")
        self.encryption_key = (os.getenv("HF_DATASET_ENCRYPTION_KEY", "") or "").strip()
        compact_raw = (os.getenv("HF_DATASET_COMPACT_AFTER_WRITE", "1") or "1").strip().lower()
        self.compact_after_write = False if compact_raw in FALSY else (compact_raw in TRUTHY or not compact_raw)
        sync_raw = (os.getenv("HF_DATASET_SYNC_INTERVAL_SECONDS", "20") or "20").strip()
        try:
            self.sync_interval_seconds = max(0.0, float(sync_raw))
        except Exception:
            self.sync_interval_seconds = 20.0
        self.repo_id = build_repo_id(self.username, self.dataset_name)
        if not self.repo_id or not self.token:
            self._enabled = False

        self._logger = logger
        self._lock = threading.RLock()
        self._missing_crypto_logged = False
        self._aesgcm_cls = None
        self._aesgcm = None
        self._git_repo_dir: str | None = None
        self._last_sync_at = 0.0

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
            return "disabled"
        mode = "optional" if self.encryption_key else "off"
        compact = "on" if self.compact_after_write else "off"
        return f"enabled: repo={self.repo_id} branch={self.branch} backend=git encryption={mode} compact={compact}"

    def get_bytes(self, path: str, *, allow_plaintext: bool = True) -> bytes | None:
        return get_bytes(self, path, allow_plaintext=allow_plaintext)

    def put_bytes(self, path: str, data: bytes, *, commit_message: str | None = None, encrypt: bool = True) -> bool:
        return put_bytes(self, path, data, commit_message=commit_message, encrypt=encrypt)

    def get_json(self, path: str, *, allow_plaintext: bool = True) -> Any | None:
        return get_json(self, path, allow_plaintext=allow_plaintext)

    def put_json(self, path: str, value: Any, *, commit_message: str | None = None, encrypt: bool = True) -> bool:
        return put_json(self, path, value, commit_message=commit_message, encrypt=encrypt)

    def resolve_repo_url(self, path: str) -> str | None:
        return resolve_repo_url(self, path)

    def delete(self, path: str, *, commit_message: str | None = None) -> bool:
        return delete_path(self, path, commit_message=commit_message)

    def delete_prefix(self, prefix: str, *, commit_message: str | None = None) -> dict:
        return delete_prefix(self, prefix, commit_message=commit_message)

    def list_paths(self, *, prefix: str = "", limit: int = 200, recursive: bool = True) -> list[dict]:
        return list_paths(self, prefix=prefix, limit=limit, recursive=recursive)

    def head(self, path: str) -> dict | None:
        return head_path(self, path)

    def exists(self, path: str) -> bool:
        return exists_path(self, path)

    def copy(self, src_path: str, dst_path: str, *, overwrite: bool = True, commit_message: str | None = None) -> bool:
        return copy_path(self, src_path, dst_path, overwrite=overwrite, commit_message=commit_message)

    def move(self, src_path: str, dst_path: str, *, overwrite: bool = True, commit_message: str | None = None) -> bool:
        return move_path(self, src_path, dst_path, overwrite=overwrite, commit_message=commit_message)
