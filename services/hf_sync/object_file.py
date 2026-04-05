"""File upload wrapper for S3-style object storage."""

from __future__ import annotations

import mimetypes

from .naming import _resolve_path
from .object_write import put_storage_object


def put_storage_file(
    user_id: int,
    *,
    file_path: str,
    name: str | None = None,
    encrypt: bool = True,
) -> dict:
    source = _resolve_path(file_path)
    if not source.exists() or not source.is_file():
        return {"ok": False, "message": f"File not found: {source}"}
    content_type = mimetypes.guess_type(str(source))[0] or "application/octet-stream"
    return put_storage_object(
        user_id,
        data=source.read_bytes(),
        name=name or source.name,
        filename=source.name,
        content_type=content_type,
        encrypt=encrypt,
    )
