"""user_cron tool — manage the calling user's scheduled tasks."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache


def _run(user_id: int, action: str, name: str, cron: str, prompt: str, enabled: bool | None) -> ToolResult:
    from domain.services.cron.matcher import is_valid_cron

    cache = get_cache()
    name = (name or "").strip()
    cron = (cron or "").strip()
    prompt = (prompt or "").strip()
    if len(name) > 120:
        return ToolResult.error("name_too_long", "name must be 120 characters or fewer")
    if len(prompt) > 20000:
        return ToolResult.error("prompt_too_long", "prompt must be 20000 characters or fewer")
    if action == "list":
        tasks = cache.get_cron_tasks(user_id)
        lines = [f"Cron tasks ({len(tasks)}):"]
        lines += [f"  {'✓' if t['enabled'] else '✗'} {t['name']} [{t['cron_expression']}] last={t.get('last_run_at')}" for t in tasks]
        return ToolResult.text("\n".join(lines))
    if action == "get":
        tasks = cache.get_cron_tasks(user_id)
        if name:
            task = next((t for t in tasks if t["name"] == name), None)
            return ToolResult.text(dumps(task)) if task else ToolResult.error("not_found", f"Task '{name}' not found")
        return ToolResult.text(dumps(tasks))
    if action == "add":
        if not name or not cron or not prompt:
            return ToolResult.error("missing_args", "name, cron, and prompt required")
        if not is_valid_cron(cron):
            return ToolResult.error("invalid_cron", "cron must be a valid five-field expression")
        if not cache.add_cron_task(user_id, name, cron, prompt):
            return ToolResult.error("not_added", f"Task '{name}' exists or the task limit was reached")
        commit()
        return ToolResult.text(f"Added cron task '{name}' [{cron}]")
    if action == "update":
        if not name:
            return ToolResult.error("missing_name", "name required")
        updates: dict = {}
        if cron:
            if not is_valid_cron(cron):
                return ToolResult.error("invalid_cron", "cron must be a valid five-field expression")
            updates["cron_expression"] = cron
        if prompt:
            updates["prompt"] = prompt
        if enabled is not None:
            updates["enabled"] = bool(enabled)
        if not updates:
            return ToolResult.error("no_updates", "Provide cron, prompt, or enabled")
        if not cache.update_cron_task(user_id, name, **updates):
            return ToolResult.error("not_found", f"Task '{name}' not found")
        commit()
        return ToolResult.text(f"Updated cron task '{name}'")
    if action == "delete":
        if not name:
            return ToolResult.error("missing_name", "name required")
        if not cache.delete_cron_task(user_id, name):
            return ToolResult.error("not_found", f"Task '{name}' not found")
        commit()
        return ToolResult.text(f"Deleted cron task '{name}'")
    return ToolResult.error("invalid_action", "action must be list, get, add, update, or delete.")


@tool(toolset="admin", side_effects=True, description="Manage the calling user's scheduled tasks: list, get, add, update, delete. add takes name+cron+prompt; update takes name plus any of cron/prompt/enabled.")
async def user_cron(
    ctx: ToolContext,
    action: Literal["list", "get", "add", "update", "delete"],
    name: Annotated[str, "Task name."] = "",
    cron: Annotated[str, "Cron expression (for add/update), e.g. '0 9 * * *'."] = "",
    prompt: Annotated[str, "Prompt to run (for add/update)."] = "",
    enabled: Annotated[bool | None, "Enable/disable (for update)."] = None,
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run, ctx.user_id, action, name, cron, prompt, enabled)
    except Exception as exc:
        return ToolResult.error("operation_failed", f"user_cron failed: {exc}")
