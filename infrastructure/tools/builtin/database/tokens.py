"""user_tokens tool — view/reset the calling user's token usage and set limits."""

from __future__ import annotations

from typing import Annotated, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache, run_tool


def _run(user_id: int, action: str, persona: str, limit: int | None) -> ToolResult:
    cache = get_cache()
    pname = (persona or "").strip() or cache.get_current_persona_name(user_id)
    if action == "get":
        return ToolResult.text(dumps(cache.get_token_usage(user_id, pname)))
    if action == "reset":
        cache.reset_token_usage(user_id, pname)
        commit()
        return ToolResult.text(f"Reset token usage for '{pname}'")
    if action == "set_limit":
        if limit is None or limit < 0:
            return ToolResult.error("bad_limit", "limit (>= 0) required")
        cache.set_token_limit(user_id, int(limit), pname)
        commit()
        return ToolResult.text(f"Set token limit to {limit} for '{pname}'")
    return ToolResult.error("invalid_action", "action must be get, reset, or set_limit.")


@tool(toolset="admin", side_effects=True, description="View or reset the calling user's token usage, or set a per-persona token limit. action: get|reset|set_limit. persona defaults to current.")
async def user_tokens(
    ctx: ToolContext,
    action: Literal["get", "reset", "set_limit"],
    persona: Annotated[str, "Persona name. Defaults to current."] = "",
    limit: Annotated[int, "Token limit (for set_limit). 0 = unlimited."] = 0,
) -> ToolResult:
    return await run_tool("user_tokens", _run, ctx.user_id, action, persona, int(limit))
