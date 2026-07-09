"""user_skill_state tool — read/write a skill's persisted runtime state."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache


def _run(user_id: int, action: str, name: str, state: Any) -> ToolResult:
    cache = get_cache()
    name = (name or "").strip()
    if not name:
        return ToolResult.error("missing_name", "skill name required")
    if action == "get":
        current = cache.get_skill_state(user_id, name)
        return ToolResult.text(dumps(current)) if current else ToolResult.error("not_found", f"No state for skill '{name}'")
    if action == "set":
        if not isinstance(state, dict):
            return ToolResult.error("bad_state", "state must be a JSON object (set {} to clear)")
        cache.set_skill_state(user_id, name, {"state": state})
        commit()
        return ToolResult.text(f"Set state for skill '{name}'")
    return ToolResult.error("invalid_action", "action must be get or set.")


@tool(toolset="admin", description="Read or overwrite a skill's persisted runtime state for the calling user. action: get|set. set takes a state object; set {} to clear.")
async def user_skill_state(
    ctx: ToolContext,
    action: Literal["get", "set"],
    name: Annotated[str, "Skill name."] = "",
    state: Annotated[Any, "JSON object to store as the skill's state (for set)."] = None,
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run, ctx.user_id, action, name, state)
    except Exception as exc:
        return ToolResult.error("operation_failed", f"user_skill_state failed: {exc}")
