"""Providers (api_presets) API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import get_user_settings, update_user_setting
from services.log_service import record_web_action
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


class ProviderSaveCurrent(BaseModel):
    name: str


def _mask_key(key: str) -> str:
    """Show first 8 chars + *** for API keys."""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:8] + "***"


def _resolve_provider_name(presets: dict, name: str) -> str | None:
    if name in presets:
        return name
    lowered = name.lower()
    for k in presets:
        if k.lower() == lowered:
            return k
    return None


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
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provider name is required")

    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    if _resolve_provider_name(presets, name) is not None:
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
    """Save current api_key/base_url/model as a named provider preset."""
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


@router.put("/{name}")
async def update_provider(
    name: str,
    body: ProviderUpdate,
    user_id: int = Depends(get_current_user),
):
    """Update an existing provider preset."""
    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    matched = _resolve_provider_name(presets, name)
    if matched is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    preset = dict(presets[matched])
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        preset[key] = value.strip() if isinstance(value, str) else value
    presets[matched] = preset
    update_user_setting(user_id, "api_presets", presets)
    record_web_action(user_id, "provider.update", {"provider": matched, "updated_keys": sorted(updates.keys())})
    return {"ok": True}


@router.delete("/{name}")
async def delete_provider(
    name: str,
    user_id: int = Depends(get_current_user),
):
    """Delete a provider preset."""
    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    matched = _resolve_provider_name(presets, name)
    if matched is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    del presets[matched]
    update_user_setting(user_id, "api_presets", presets)
    record_web_action(user_id, "provider.delete", {"provider": matched})
    return {"ok": True}


@router.post("/{name}/load")
async def load_provider(
    name: str,
    user_id: int = Depends(get_current_user),
):
    """Load a provider's settings into the current configuration."""
    settings = get_user_settings(user_id)
    presets = settings.get("api_presets", {})
    matched = _resolve_provider_name(presets, name)
    if matched is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    preset = presets[matched]
    update_user_setting(user_id, "base_url", preset.get("base_url", ""))
    update_user_setting(user_id, "model", preset.get("model", ""))
    # Only update api_key if the preset has one
    if preset.get("api_key"):
        update_user_setting(user_id, "api_key", preset["api_key"])
    record_web_action(user_id, "provider.load", {"provider": matched})
    return {"ok": True}
