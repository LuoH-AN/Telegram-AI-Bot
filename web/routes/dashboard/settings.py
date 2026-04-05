"""Settings API routes."""

from fastapi import APIRouter, Depends, HTTPException

from services import get_user_settings, update_user_setting
from services.log import record_web_action
from web.auth import get_current_user
from web.routes.dashboard.settings_schema import ALLOWED_FIELDS, SettingsUpdate, mask_key

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(user_id: int = Depends(get_current_user)):
    settings = get_user_settings(user_id)
    safe = dict(settings)
    api_key = safe.pop("api_key", "") or ""
    safe["has_api_key"] = bool(api_key)
    safe["api_key_masked"] = mask_key(api_key)
    safe["stream_mode"] = safe.get("stream_mode", "") or ""
    return safe


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    user_id: int = Depends(get_current_user),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True, "updated": []}

    unknown = [k for k in updates if k not in ALLOWED_FIELDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported settings field(s): {', '.join(unknown)}")

    for key, value in updates.items():
        if key == "api_key":
            value = value.strip()
        elif isinstance(value, str):
            value = value.strip()
        update_user_setting(user_id, key, value)

    record_web_action(
        user_id=user_id,
        action="settings.update",
        detail={"updated_keys": sorted(updates.keys())},
    )
    return {"ok": True, "updated": sorted(updates.keys())}
