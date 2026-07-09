"""user_settings tool — read/write the calling user's AI settings."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import USER_DATA_INSTRUCTION, commit, dumps, get_cache


def _run(user_id: int, action: str, key: str, value: Any) -> ToolResult:
    cache = get_cache()
    if action == "list":
        settings = cache.get_settings(user_id)
        return ToolResult.text("\n".join(f"  {k} = {dumps(v, indent=False)}" for k, v in settings.items()))
    if action == "get":
        settings = cache.get_settings(user_id)
        if key:
            return ToolResult.text(f"{key} = {dumps(settings.get(key))}")
        return ToolResult.text(dumps(settings))
    if action == "set":
        if not key:
            return ToolResult.error("missing_key", "key required for set")
        cache.update_settings(user_id, key, value)
        commit()
        return ToolResult.text(f"Updated settings.{key} = {dumps(value, indent=False)}")
    return ToolResult.error("invalid_action", "action must be list, get, or set.")


@tool(toolset="admin", instruction=USER_DATA_INSTRUCTION, description="Read or change the calling user's own AI settings (api_key, base_url, model, temperature, reasoning_effort, token_limit, current_persona, global_prompt, tts_*, title_model, cron_model, ...). action: list|get|set. Set a field to \"\" to clear it.")
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
