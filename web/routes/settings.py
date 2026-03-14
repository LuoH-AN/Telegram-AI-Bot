"""Settings API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from services import get_user_settings, update_user_setting, normalize_tts_endpoint
from services.log import record_web_action
from utils.tooling import AVAILABLE_TOOLS, normalize_tools_csv
from web.auth import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_FIELDS = {
    "api_key",
    "base_url",
    "model",
    "temperature",
    "reasoning_effort",
    "show_thinking",
    "stream_mode",
    "enabled_tools",
    "cron_enabled_tools",
    "tts_voice",
    "tts_style",
    "tts_endpoint",
    "title_model",
    "cron_model",
    "global_prompt",
}
ALLOWED_REASONING_EFFORTS = {"", "none", "minimal", "low", "medium", "high", "xhigh"}
ALLOWED_STREAM_MODES = {"", "default", "time", "chars"}
CLEARABLE_VALUES = {"off", "clear", "none"}


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:8] + "***"


class SettingsUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None
    show_thinking: bool | None = None
    stream_mode: str | None = None
    enabled_tools: str | None = None
    cron_enabled_tools: str | None = None
    tts_voice: str | None = None
    tts_style: str | None = None
    tts_endpoint: str | None = None
    title_model: str | None = None
    cron_model: str | None = None
    global_prompt: str | None = None

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value < 0.0 or value > 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return value

    @field_validator("reasoning_effort")
    @classmethod
    def validate_reasoning_effort(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized in {"off", "clear"}:
            normalized = ""
        if normalized not in ALLOWED_REASONING_EFFORTS:
            raise ValueError(
                "reasoning_effort must be one of: none, minimal, low, medium, high, xhigh, clear"
            )
        return normalized

    @field_validator("stream_mode")
    @classmethod
    def validate_stream_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized in {"off", "clear", "none"}:
            normalized = ""
        if normalized not in ALLOWED_STREAM_MODES:
            raise ValueError("stream_mode must be one of: default, time, chars, clear")
        return normalized

    @field_validator("enabled_tools", "cron_enabled_tools")
    @classmethod
    def validate_tools_csv(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return normalize_tools_csv(value)

    @field_validator("tts_style")
    @classmethod
    def normalize_tts_style(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower()

    @field_validator("tts_endpoint")
    @classmethod
    def validate_tts_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            return ""
        if text.lower() in {"auto", "default"} | CLEARABLE_VALUES:
            return ""
        normalized = normalize_tts_endpoint(text)
        if not normalized:
            raise ValueError("Invalid tts_endpoint")
        return normalized

    @field_validator("title_model", "cron_model")
    @classmethod
    def normalize_optional_model(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if text.lower() in CLEARABLE_VALUES:
            return ""
        return text


@router.get("")
async def get_settings(user_id: int = Depends(get_current_user)):
    """Return user settings with safe api_key fields for UI."""
    settings = get_user_settings(user_id)
    safe = dict(settings)
    api_key = safe.pop("api_key", "") or ""
    safe["has_api_key"] = bool(api_key)
    safe["api_key_masked"] = _mask_key(api_key)
    safe["stream_mode"] = safe.get("stream_mode", "") or ""
    safe["available_tools"] = list(AVAILABLE_TOOLS)
    return safe


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    user_id: int = Depends(get_current_user),
):
    """Partially update user settings."""
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
