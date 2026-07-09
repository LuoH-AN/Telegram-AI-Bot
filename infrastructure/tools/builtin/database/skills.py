"""user_skills tool — view/toggle/delete the calling user's installed skills."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache


def _run(user_id: int, action: str, name: str, enabled: bool | None) -> ToolResult:
    cache = get_cache()
    name = (name or "").strip()
    if action == "list":
        skills = cache.get_skills(user_id)
        lines = [f"Skills ({len(skills)}):"]
        lines += [f"  {'✓' if s.get('enabled') else '✗'} {s['name']} — {s.get('display_name', s['name'])}" for s in skills]
        return ToolResult.text("\n".join(lines))
    if action == "get":
        if name:
            skill = cache.get_skill(user_id, name)
            return ToolResult.text(dumps(skill)) if skill else ToolResult.error("not_found", f"Skill '{name}' not found")
        return ToolResult.text(dumps(cache.get_skills(user_id)))
    if action == "toggle":
        if not name:
            return ToolResult.error("missing_name", "name required")
        skill = cache.get_skill(user_id, name)
        if not skill:
            return ToolResult.error("not_found", f"Skill '{name}' not found")
        new_enabled = (not skill.get("enabled", True)) if enabled is None else bool(enabled)
        cache.update_skill(user_id, name, enabled=new_enabled)
        commit()
        return ToolResult.text(f"Skill '{name}' {'enabled' if new_enabled else 'disabled'}")
    if action == "delete":
        if not name:
            return ToolResult.error("missing_name", "name required")
        if not cache.delete_skill(user_id, name):
            return ToolResult.error("not_found", f"Skill '{name}' not found")
        commit()
        return ToolResult.text(f"Deleted skill '{name}' (use /skill remove for full uninstall)")
    return ToolResult.error("invalid_action", "action must be list, get, toggle, or delete.")


@tool(toolset="admin", description="View or change the calling user's installed skills: list, get, toggle, delete. toggle flips enabled, or set it explicitly with enabled.")
async def user_skills(
    ctx: ToolContext,
    action: Literal["list", "get", "toggle", "delete"],
    name: Annotated[str, "Skill name."] = "",
    enabled: Annotated[bool | None, "Force enable/disable for toggle. Omit to flip."] = None,
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run, ctx.user_id, action, name, enabled)
    except Exception as exc:
        return ToolResult.error("operation_failed", f"user_skills failed: {exc}")
