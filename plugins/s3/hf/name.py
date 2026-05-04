"""Path and key helpers for S3-style object storage service."""

from __future__ import annotations

import hashlib
from pathlib import Path

from plugins.terminal.state import REPO_ROOT

INDEX_NAMESPACE = ".hf_sync/index"


def _normalize_object_key(key: str | None, *, default: str = "object.dat") -> str:
    """Normalize an object key while preserving S3-like path semantics."""
    raw = (key or "").strip().replace("\\", "/")
    if not raw:
        return default
    text = raw.lstrip("/")
    parts = [part.strip() for part in text.split("/") if part.strip() not in {"", "."}]
    if not parts:
        return default

    safe_parts: list[str] = []
    for part in parts:
        if part == "..":
            continue
        safe_chars = []
        for ch in part:
            if ch.isalnum() or ch in {"-", "_", ".", "@", "+", "="}:
                safe_chars.append(ch)
            else:
                safe_chars.append("_")
        sanitized = "".join(safe_chars).strip("._")
        if sanitized:
            safe_parts.append(sanitized)
    if not safe_parts:
        return default
    return "/".join(safe_parts)


def _resolve_path(path: str | None) -> Path:
    raw = (path or "").strip()
    if not raw:
        return REPO_ROOT
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate.resolve()


def _object_index_path(user_id: int) -> str:
    return f"{INDEX_NAMESPACE}/{int(user_id)}.json"


def _meta_key_for_path(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
