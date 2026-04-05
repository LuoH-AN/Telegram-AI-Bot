"""Path and repo-id helpers."""

from __future__ import annotations

from pathlib import PurePosixPath


def clean_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip().lstrip("/")
    if not value:
        raise ValueError("path is empty")
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe path: {path!r}")
    return "/".join(parts)


def build_repo_id(username: str, dataset_name: str) -> str:
    if not dataset_name:
        return ""
    if "/" in dataset_name:
        return dataset_name.strip("/")
    if username:
        return f"{username}/{dataset_name}"
    return ""


def prefixed_path(store, path: str) -> str:
    clean = clean_path(path)
    return f"{store.prefix}/{clean}" if store.prefix else clean
