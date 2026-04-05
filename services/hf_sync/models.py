"""Data models for HF object storage service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectRecord:
    object_name: str
    content_path: str
    meta_path: str
    content_type: str
    filename: str
    encrypted: bool
    size: int
    created_at: float
