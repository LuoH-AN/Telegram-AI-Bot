"""Store class facade used by hf_sync."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from .bytes_ops import get_bytes, put_bytes
from .constants import FALSY, TRUTHY
from .delete_ops import delete_path
from .json_ops import get_json, put_json, resolve_repo_url
from .paths import build_repo_id

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
        self.repo_id = build_repo_id(self.username, self.dataset_name)
        if not self.repo_id or not self.token or not self.encryption_key:
            self._enabled = False

        self._logger = logger
        self._lock = threading.RLock()
        self._missing_crypto_logged = False
        self._aesgcm_cls = None
        self._aesgcm = None
        self._git_repo_dir: str | None = None

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

    def get_bytes(self, path: str, *, allow_plaintext: bool = False) -> bytes | None:
        return get_bytes(self, path, allow_plaintext=allow_plaintext)

    def put_bytes(self, path: str, data: bytes, *, commit_message: str | None = None, encrypt: bool = True) -> bool:
        return put_bytes(self, path, data, commit_message=commit_message, encrypt=encrypt)

    def get_json(self, path: str, *, allow_plaintext: bool = False) -> Any | None:
        return get_json(self, path, allow_plaintext=allow_plaintext)

    def put_json(self, path: str, value: Any, *, commit_message: str | None = None, encrypt: bool = True) -> bool:
        return put_json(self, path, value, commit_message=commit_message, encrypt=encrypt)

    def resolve_repo_url(self, path: str) -> str | None:
        return resolve_repo_url(self, path)

    def delete(self, path: str, *, commit_message: str | None = None) -> bool:
        return delete_path(self, path, commit_message=commit_message)
