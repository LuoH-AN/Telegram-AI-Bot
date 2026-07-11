"""user_settings tool — read/write the calling user's AI settings."""

from __future__ import annotations

import asyncio
import copy
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import USER_DATA_INSTRUCTION, commit, dumps, get_cache

_SENSITIVE_PARTS = ("api_key", "token", "secret", "password", "credential")
_PROTECTED_KEYS = {"terminal_approvals"}
_ALLOWED_KEYS = {
    "api_key", "base_url", "model", "temperature", "reasoning_effort", "show_thinking",
    "token_limit", "current_persona", "stream_mode", "busy_mode", "tool_progress",
    "api_presets", "title_model", "cron_model", "global_prompt", "timezone", "ux_language",
}


def _validated_value(cache, user_id: int, key: str, value: Any) -> Any:
    from infrastructure.config import VALID_REASONING_EFFORTS
    from infrastructure.config.telegram_ux import VALID_TELEGRAM_BUSY_MODES, VALID_TELEGRAM_TOOL_PROGRESS

    if key not in _ALLOWED_KEYS:
        raise ValueError(f"unsupported settings key: {key}")
    if key in {"api_key", "model", "title_model", "cron_model", "global_prompt"}:
        if not isinstance(value, str):
            raise ValueError(f"settings.{key} must be a string")
        return value[:20000] if key == "global_prompt" else value[:1000]
    if key == "base_url":
        if not isinstance(value, str) or urlparse(value).scheme not in {"http", "https"}:
            raise ValueError("settings.base_url must be an HTTP(S) URL")
        return value.rstrip("/")
    if key == "temperature":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("settings.temperature must be a number")
        number = float(value)
        if not 0 <= number <= 2:
            raise ValueError("settings.temperature must be between 0 and 2")
        return number
    if key in {"show_thinking"}:
        if not isinstance(value, bool):
            raise ValueError(f"settings.{key} must be a boolean")
        return value
    if key == "token_limit":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("settings.token_limit must be a non-negative integer")
        return value
    if key == "reasoning_effort":
        normalized = str(value or "").strip().lower()
        if normalized and normalized not in VALID_REASONING_EFFORTS:
            raise ValueError("invalid reasoning_effort")
        return normalized
    if key == "stream_mode":
        normalized = str(value or "").strip().lower()
        if normalized not in {"", "default", "time", "chars", "off"}:
            raise ValueError("invalid stream_mode")
        return normalized
    if key == "busy_mode":
        normalized = str(value or "").strip().lower()
        if normalized not in VALID_TELEGRAM_BUSY_MODES:
            raise ValueError("invalid busy_mode")
        return normalized
    if key == "tool_progress":
        normalized = str(value or "").strip().lower()
        if normalized not in VALID_TELEGRAM_TOOL_PROGRESS:
            raise ValueError("invalid tool_progress")
        return normalized
    if key == "current_persona":
        normalized = str(value or "").strip()
        if normalized not in cache.get_personas(user_id):
            raise ValueError(f"persona '{normalized}' does not exist")
        return normalized
    if key == "api_presets":
        if not isinstance(value, dict):
            raise ValueError("settings.api_presets must be an object")
        return value
    if key == "timezone":
        normalized = str(value or "").strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("invalid timezone") from None
        return normalized
    if key == "ux_language":
        normalized = str(value or "").strip().lower()
        if normalized not in {"", "en", "zh"}:
            raise ValueError("ux_language must be '', 'en', or 'zh'")
        return normalized
    return value


def _redact(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if lowered in _PROTECTED_KEYS:
        return "<managed by terminal approval buttons>"
    if any(part in lowered for part in _SENSITIVE_PARTS):
        return "<redacted>" if value not in (None, "") else value
    if isinstance(value, dict):
        return {item_key: _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _run(user_id: int, action: str, key: str, value: Any) -> ToolResult:
    cache = get_cache()
    if action == "list":
        settings = cache.get_settings(user_id)
        return ToolResult.text("\n".join(f"  {k} = {dumps(_redact(v, k), indent=False)}" for k, v in settings.items()))
    if action == "get":
        settings = cache.get_settings(user_id)
        if key:
            return ToolResult.text(f"{key} = {dumps(_redact(settings.get(key), key))}")
        return ToolResult.text(dumps(_redact(settings)))
    if action == "set":
        if not key:
            return ToolResult.error("missing_key", "key required for set")
        if key.lower() in _PROTECTED_KEYS:
            return ToolResult.error("protected_setting", f"settings.{key} can only be changed through terminal approval controls")
        try:
            normalized = _validated_value(cache, user_id, key, value)
        except ValueError as exc:
            return ToolResult.error("invalid_value", str(exc))
        settings = cache.get_settings(user_id)
        previous = copy.deepcopy(settings.get(key))
        dirty = getattr(cache, "_dirty_settings", None)
        was_dirty = bool(dirty is not None and user_id in dirty)
        cache.update_settings(user_id, key, normalized)
        try:
            commit()
        except Exception:
            settings[key] = previous
            if dirty is not None and not was_dirty:
                dirty.discard(user_id)
            raise
        return ToolResult.text(f"Updated settings.{key} = {dumps(_redact(normalized, key), indent=False)}")
    return ToolResult.error("invalid_action", "action must be list, get, or set.")


@tool(toolset="admin", side_effects=True, instruction=USER_DATA_INSTRUCTION, description="Read or change validated AI settings for the calling user. Unknown keys and invalid values are rejected; credentials are redacted.")
async def user_settings(
    ctx: ToolContext,
    action: Literal["list", "get", "set"],
    key: Annotated[str, "Settings key (for get/set). Omit for the full object."] = "",
    value: Annotated[Any, "Value to set."] = None,
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run, ctx.user_id, action, (key or "").strip(), value)
    except Exception as exc:
        return ToolResult.error("operation_failed", f"user_settings failed: {exc}")
