"""Providers (api_presets) API routes."""

from fastapi import APIRouter, Depends, HTTPException

from services import get_user_settings, update_user_setting
from services.log import record_web_action
from web.auth import get_current_user
from web.routes.dashboard.providers_schema import (
    ProviderCreate,
    ProviderSaveCurrent,
    mask_key,
    resolve_provider_name,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
async def list_providers(user_id: int = Depends(get_current_user)):
    settings = get_user_settings(user_id)
    presets = settings.get("api_presets", {})
    result = {
        name: {
            "name": name,
            "api_key": mask_key(preset.get("api_key", "")),
            "base_url": preset.get("base_url", ""),
            "model": preset.get("model", ""),
        }
        for name, preset in presets.items()
    }
    return {"providers": result}


@router.post("")
async def create_provider(
    body: ProviderCreate,
    user_id: int = Depends(get_current_user),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provider name is required")

    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    if resolve_provider_name(presets, name) is not None:
        raise HTTPException(status_code=409, detail="Provider already exists")
    presets[name] = {
        "api_key": body.api_key.strip(),
        "base_url": body.base_url.strip(),
        "model": body.model.strip(),
    }
    update_user_setting(user_id, "api_presets", presets)
    record_web_action(user_id, "provider.create", {"provider": name})
    return {"ok": True}


@router.post("/save-current")
async def save_current_provider(
    body: ProviderSaveCurrent,
    user_id: int = Depends(get_current_user),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provider name is required")

    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    presets[name] = {
        "api_key": settings.get("api_key", ""),
        "base_url": settings.get("base_url", ""),
        "model": settings.get("model", ""),
    }
    update_user_setting(user_id, "api_presets", presets)
    record_web_action(user_id, "provider.save_current", {"provider": name})
    return {"ok": True}


from . import providers_manage
