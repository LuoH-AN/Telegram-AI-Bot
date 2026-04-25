"""Artifact URL helpers for S3-style object storage."""

from __future__ import annotations

from config import WEB_BASE_URL
from web.auth import create_artifact_token

from .record import ObjectRecord


def _artifact_view_url(record: ObjectRecord, *, user_id: int) -> str:
    token = create_artifact_token(
        user_id=user_id,
        path=record.content_path,
        content_type=record.content_type,
        filename=record.filename,
        encrypted=record.encrypted,
    )
    return f"{WEB_BASE_URL.rstrip('/')}/artifacts/{token}"
