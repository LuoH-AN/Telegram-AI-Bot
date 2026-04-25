"""Artifact download route."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from services.hf.store import get_hf_dataset_store
from web.auth import verify_artifact_token

router = APIRouter(tags=["artifacts"])


def _candidate_paths(path: str) -> list[str]:
    raw = (path or "").strip()
    if not raw:
        return []
    candidates: list[str] = []

    def _add(value: str) -> None:
        text = value.strip()
        if text and text not in candidates:
            candidates.append(text)

    _add(raw)
    _add(raw.lstrip("/"))
    if raw.startswith("/."):
        _add(raw[1:])
    if raw.startswith("/hf_sync/"):
        _add("." + raw)
    if raw.startswith("hf_sync/"):
        _add("." + raw)
    if raw.startswith("/.hf_sync/"):
        _add(raw[1:])
    # S3 storage paths
    if raw.startswith("/.s3/"):
        _add(raw[1:])
    if raw.startswith(".s3/"):
        _add(raw)
    if raw.startswith("/s3/"):
        _add("." + raw)
    if raw.startswith("s3/"):
        _add("." + raw)
    return candidates


@router.get("/artifacts/{token}")
async def get_artifact(token: str):
    payload = verify_artifact_token(token)
    store = get_hf_dataset_store()
    if not store.enabled:
        raise HTTPException(status_code=503, detail="Artifact storage unavailable")

    encrypted = bool(payload.get("encrypted", True))
    content_type = str(payload.get("content_type") or "application/octet-stream")
    filename = str(payload.get("filename") or "").strip() or "artifact.bin"
    for path in _candidate_paths(str(payload.get("path") or "")):
        data = store.get_bytes(path, allow_plaintext=not encrypted)
        if data is None:
            continue
        headers = {"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "private, max-age=300"}
        return Response(content=data, media_type=content_type, headers=headers)
    raise HTTPException(status_code=404, detail="Artifact not found")
