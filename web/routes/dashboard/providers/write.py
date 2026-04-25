"""Provider mutation routes: update/delete/load."""

from fastapi import Depends, HTTPException

from services import get_user_settings, update_user_setting
from services.log import record_web_action
from web.auth import get_current_user
from .schema import ProviderUpdate, resolve_provider_name

from .route import router


@router.put("/{name}")
async def update_provider(name: str, body: ProviderUpdate, user_id: int = Depends(get_current_user)):
    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    matched = resolve_provider_name(presets, name)
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
async def delete_provider(name: str, user_id: int = Depends(get_current_user)):
    settings = get_user_settings(user_id)
    presets = dict(settings.get("api_presets", {}))
    matched = resolve_provider_name(presets, name)
    if matched is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    del presets[matched]
    update_user_setting(user_id, "api_presets", presets)
    record_web_action(user_id, "provider.delete", {"provider": matched})
    return {"ok": True}


@router.post("/{name}/load")
async def load_provider(name: str, user_id: int = Depends(get_current_user)):
    settings = get_user_settings(user_id)
    presets = settings.get("api_presets", {})
    matched = resolve_provider_name(presets, name)
    if matched is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    preset = presets[matched]
    update_user_setting(user_id, "base_url", preset.get("base_url", ""))
    update_user_setting(user_id, "model", preset.get("model", ""))
    if preset.get("api_key"):
        update_user_setting(user_id, "api_key", preset["api_key"])
    record_web_action(user_id, "provider.load", {"provider": matched})
    return {"ok": True}
