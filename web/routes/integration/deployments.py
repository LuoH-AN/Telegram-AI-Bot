"""Public routes for deployed static projects."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.deployments import deployment_dir, get_deployment, safe_child

router = APIRouter(tags=["deployments"])


def _resolve_target(slug: str, asset_path: str = ""):
    manifest = get_deployment(slug)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    root = deployment_dir(slug)
    requested = manifest.get("entry_path") if not asset_path else asset_path
    target = safe_child(root, requested or "index.html")
    if target.is_file():
        return target
    fallback = root / "index.html"
    if asset_path and fallback.exists():
        return fallback
    raise HTTPException(status_code=404, detail="Deployment asset not found")


@router.get("/deploy/{slug}")
async def get_deployment_index(slug: str):
    target = _resolve_target(slug)
    return FileResponse(target, headers={"Cache-Control": "no-store"})


@router.get("/deploy/{slug}/{asset_path:path}")
async def get_deployment_asset(slug: str, asset_path: str):
    if asset_path.startswith("."):
        raise HTTPException(status_code=404, detail="Deployment asset not found")
    target = _resolve_target(slug, asset_path)
    return FileResponse(target, headers={"Cache-Control": "no-store"})
