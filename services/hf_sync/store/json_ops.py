"""JSON operations and URL resolver."""

from __future__ import annotations

import json
from typing import Any

from .bytes_ops import get_bytes, put_bytes
from .paths import prefixed_path


def get_json(store, path: str, *, allow_plaintext: bool = False) -> Any | None:
    raw = get_bytes(store, path, allow_plaintext=allow_plaintext)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        store._logger.warning("HF store get_json parse failed for %s: %s", path, exc)
        return None


def put_json(
    store,
    path: str,
    value: Any,
    *,
    commit_message: str | None = None,
    encrypt: bool = True,
) -> bool:
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except Exception as exc:
        store._logger.warning("HF store put_json encode failed for %s: %s", path, exc)
        return False
    return put_bytes(store, path, raw, commit_message=commit_message, encrypt=encrypt)


def resolve_repo_url(store, path: str) -> str | None:
    if not store._enabled or not store.repo_id:
        return None
    try:
        filename = prefixed_path(store, path)
    except ValueError:
        return None
    return f"https://huggingface.co/datasets/{store.repo_id}/resolve/{store.branch}/{filename}"
