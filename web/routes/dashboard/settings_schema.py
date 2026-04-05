"""Schemas and constants for settings routes."""
from pydantic import BaseModel, field_validator

ALLOWED_FIELDS = {"api_key", "base_url", "model", "temperature", "reasoning_effort", "show_thinking", "stream_mode", "title_model", "cron_model", "global_prompt"}
ALLOWED_REASONING_EFFORTS = {"", "none", "minimal", "low", "medium", "high", "xhigh"}
ALLOWED_STREAM_MODES = {"", "default", "time", "chars", "off"}
CLEARABLE_VALUES = {"off", "clear", "none"}


def mask_key(key: str) -> str:
    if not key: return ""
    return key[:2] + "***" if len(key) <= 8 else key[:8] + "***"


class SettingsUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None
    show_thinking: bool | None = None
    stream_mode: str | None = None
    title_model: str | None = None
    cron_model: str | None = None
    global_prompt: str | None = None

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float | None) -> float | None:
        if value is None or 0.0 <= value <= 2.0:
            return value
        raise ValueError("temperature must be between 0.0 and 2.0")

    @field_validator("reasoning_effort")
    @classmethod
    def validate_reasoning_effort(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized in {"off", "clear"}:
            normalized = ""
        if normalized not in ALLOWED_REASONING_EFFORTS:
            raise ValueError("reasoning_effort must be one of: none, minimal, low, medium, high, xhigh, clear")
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

    @field_validator("title_model", "cron_model")
    @classmethod
    def normalize_optional_model(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        return "" if text.lower() in CLEARABLE_VALUES else text
