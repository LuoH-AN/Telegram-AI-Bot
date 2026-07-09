"""user_personas tool — manage the calling user's personas."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache


def _run(user_id: int, action: str, name: str, prompt: str) -> ToolResult:
    cache = get_cache()
    name = (name or "").strip()
    if action == "list":
        personas = cache.get_personas(user_id)
        current = cache.get_current_persona_name(user_id)
        lines = [f"Personas ({len(personas)}):"]
        lines += [f"  {n}{' *' if n == current else ''}" for n in personas]
        return ToolResult.text("\n".join(lines))
    if action == "get":
        personas = cache.get_personas(user_id)
        if name:
            persona = personas.get(name)
            return ToolResult.text(dumps(persona)) if persona else ToolResult.error("not_found", f"Persona '{name}' not found")
        return ToolResult.text(dumps(list(personas.values())))
    if action == "create":
        if not name or not prompt:
            return ToolResult.error("missing_args", "name and prompt required")
        if not cache.create_persona(user_id, name, prompt):
            return ToolResult.error("exists", f"Persona '{name}' already exists")
        commit()
        return ToolResult.text(f"Created persona '{name}'")
    if action == "edit":
        if not name or not prompt:
            return ToolResult.error("missing_args", "name and prompt required")
        if not cache.update_persona_prompt(user_id, name, prompt):
            return ToolResult.error("not_found", f"Persona '{name}' not found")
        commit()
        return ToolResult.text(f"Updated persona '{name}'")
    if action == "delete":
        if not name:
            return ToolResult.error("missing_name", "name required")
        if not cache.delete_persona(user_id, name):
            return ToolResult.error("not_deleted", f"Cannot delete '{name}' (default or not found)")
        commit()
        return ToolResult.text(f"Deleted persona '{name}'")
    if action == "switch":
        if not name:
            return ToolResult.error("missing_name", "name required")
        if name not in cache.get_personas(user_id):
            return ToolResult.error("not_found", f"Persona '{name}' not found")
        cache.set_current_persona(user_id, name)
        commit()
        return ToolResult.text(f"Switched to persona '{name}'")
    return ToolResult.error("invalid_action", "action must be list, get, create, edit, delete, or switch.")


@tool(toolset="admin", description="Manage the calling user's personas: list, get, create, edit, delete, switch. 'default' cannot be deleted.")
async def user_personas(
    ctx: ToolContext,
    action: Literal["list", "get", "create", "edit", "delete", "switch"],
    name: Annotated[str, "Persona name."] = "",
    prompt: Annotated[str, "system_prompt text (for create/edit)."] = "",
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run, ctx.user_id, action, name, prompt)
    except Exception as exc:
        return ToolResult.error("operation_failed", f"user_personas failed: {exc}")
