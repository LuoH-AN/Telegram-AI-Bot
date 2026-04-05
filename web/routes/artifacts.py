"""Artifact viewing routes backed by HF dataset storage."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from hf_dataset_store import get_hf_dataset_store
from web.auth import verify_artifact_token

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{token}")
async def artifact_view(token: str):
    payload = verify_artifact_token(token)
    path = str(payload.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=404, detail="Artifact path missing")

    store = get_hf_dataset_store()
    if not store.enabled:
        raise HTTPException(status_code=503, detail="HF storage unavailable")

    raw = store.get_bytes(path, allow_plaintext=True)
    if raw is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    content_type = str(payload.get("content_type") or "application/octet-stream")
    filename = str(payload.get("filename") or "").strip()
    headers = {"Cache-Control": "private, max-age=300"}
    if filename:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return Response(content=raw, media_type=content_type, headers=headers)
