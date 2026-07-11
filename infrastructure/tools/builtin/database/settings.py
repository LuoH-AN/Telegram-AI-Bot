"""user_settings tool — read/write the calling user's AI settings."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import USER_DATA_INSTRUCTION, commit, dumps, get_cache

_SENSITIVE_PARTS = ("api_key", "token", "secret", "password", "credential")
_PROTECTED_KEYS = {"terminal_approvals"}


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
        cache.update_settings(user_id, key, value)
        commit()
        return ToolResult.text(f"Updated settings.{key} = {dumps(_redact(value, key), indent=False)}")
    return ToolResult.error("invalid_action", "action must be list, get, or set.")


@tool(toolset="admin", instruction=USER_DATA_INSTRUCTION, description="Read or change the calling user's own AI settings (api_key, base_url, model, temperature, reasoning_effort, token_limit, current_persona, global_prompt, title_model, cron_model, ...). action: list|get|set. Set a field to \"\" to clear it.")
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
