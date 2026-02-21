"""Settings API routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services import get_user_settings, update_user_setting
from web.auth import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_FIELDS = {
    "base_url", "model", "temperature", "token_limit",
    "enabled_tools", "tts_voice", "tts_style", "tts_endpoint", "title_model",
}


class SettingsUpdate(BaseModel):
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None
    token_limit: int | None = None
    enabled_tools: str | None = None
    tts_voice: str | None = None
    tts_style: str | None = None
    tts_endpoint: str | None = None
    title_model: str | None = None


@router.get("")
async def get_settings(user_id: int = Depends(get_current_user)):
    """Return user settings (excluding api_key)."""
    settings = get_user_settings(user_id)
    safe = {k: v for k, v in settings.items() if k != "api_key"}
    return safe


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    user_id: int = Depends(get_current_user),
):
    """Partially update user settings."""
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key in ALLOWED_FIELDS:
            update_user_setting(user_id, key, value)
    return {"ok": True}
