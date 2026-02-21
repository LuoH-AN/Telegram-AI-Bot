"""Providers (api_presets) API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import get_user_settings, update_user_setting
from web.auth import get_current_user

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    api_key: str
    base_url: str
    model: str = ""


class ProviderUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


def _mask_key(key: str) -> str:
    """Show first 8 chars + *** for API keys."""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:8] + "***"


@router.get("")
async def list_providers(user_id: int = Depends(get_current_user)):
    """Return all api_presets with masked API keys."""
    settings = get_user_settings(user_id)
    presets = settings.get("api_presets", {})
    result = {}
    for name, preset in presets.items():
        result[name] = {
            "name": name,
            "api_key": _mask_key(preset.get("api_key", "")),
            "base_url": preset.get("base_url", ""),
            "model": preset.get("model", ""),
        }
    return {"providers": result}


@router.post("")
async def create_provider(
    body: ProviderCreate,
    user_id: int = Depends(get_current_user),
):
    """Create a new provider preset."""
    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    if body.name in presets:
        raise HTTPException(status_code=409, detail="Provider already exists")
    presets[body.name] = {
        "api_key": body.api_key,
        "base_url": body.base_url,
        "model": body.model,
    }
    update_user_setting(user_id, "api_presets", presets)
    return {"ok": True}


@router.put("/{name}")
async def update_provider(
    name: str,
    body: ProviderUpdate,
    user_id: int = Depends(get_current_user),
):
    """Update an existing provider preset."""
    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    if name not in presets:
        raise HTTPException(status_code=404, detail="Provider not found")
    preset = dict(presets[name])
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        preset[key] = value
    presets[name] = preset
    update_user_setting(user_id, "api_presets", presets)
    return {"ok": True}


@router.delete("/{name}")
async def delete_provider(
    name: str,
    user_id: int = Depends(get_current_user),
):
    """Delete a provider preset."""
    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    if name not in presets:
        raise HTTPException(status_code=404, detail="Provider not found")
    del presets[name]
    update_user_setting(user_id, "api_presets", presets)
    return {"ok": True}


@router.post("/{name}/load")
async def load_provider(
    name: str,
    user_id: int = Depends(get_current_user),
):
    """Load a provider's settings into the current configuration."""
    settings = get_user_settings(user_id)
    presets = settings.get("api_presets", {})
    if name not in presets:
        raise HTTPException(status_code=404, detail="Provider not found")
    preset = presets[name]
    update_user_setting(user_id, "base_url", preset.get("base_url", ""))
    update_user_setting(user_id, "model", preset.get("model", ""))
    # Only update api_key if the preset has one
    if preset.get("api_key"):
        update_user_setting(user_id, "api_key", preset["api_key"])
    return {"ok": True}
