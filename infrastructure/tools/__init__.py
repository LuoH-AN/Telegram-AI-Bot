"""Public tool API: discovery, definitions, async execution, instructions.

Drop-in surface matching the old infrastructure.plugins facade, so the chat
pipeline switches with a one-line import change. process_tool_calls is async:
callers must `await` it (no asyncio.to_thread wrapper).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from .core.availability import check_available
from .core.context import ToolContext, ToolResult
from .core.discovery import discover as _discover_native
from .core.registry import ToolEntry, registry

from infrastructure.config import is_admin

logger = logging.getLogger(__name__)
_DISCOVERED = False


def _default_context(user_id: int) -> ToolContext:
    outbound = None
    try:
        from adapters.telegram.outbound import get_outbound
        outbound = get_outbound()
    except Exception:
        outbound = None
    sender = getattr(outbound, "sender", None)
    update = getattr(sender, "update", None)
    chat = getattr(update, "effective_chat", None)
    confirm = getattr(sender, "request_terminal_approval", None)
    return ToolContext(
        user_id=user_id,
        chat_id=getattr(chat, "id", None),
        outbound=outbound,
        confirm=confirm if callable(confirm) else None,
    )


def _ensure_discovered() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    try:
        _discover_native()
        _bridge_skills()
        _bridge_mcp()
    except Exception:
        logger.exception("tool discovery failed")
        return
    _DISCOVERED = True


def _bridge_mcp() -> None:
    """Register remote MCP server tools. Runs in a thread; best-effort."""
    try:
        import asyncio

        from .mcp.registry import discover_mcp
        asyncio.get_event_loop()
    except Exception:
        return
    import threading

    def _run():
        try:
            discover_mcp()
        except Exception:
            logger.warning("MCP discovery failed", exc_info=True)

    threading.Thread(target=_run, daemon=True, name="mcp-discover").start()


def _bridge_skills() -> None:
    """Prompt-only skills (no native functions) contribute system-prompt instructions only."""
    try:
        from infrastructure.tools.skills.manager import get_skill_manager
        get_skill_manager().discover()
    except Exception:
        logger.warning("skill discovery failed", exc_info=True)


def _user_enabled(user_id: int | None, skill: str | None) -> bool:
    if user_id is None or not skill:
        return True
    try:
        from infrastructure.cache import cache
        lowered = skill.lower()
        for row in cache.get_skills(user_id):
            if str(row.get("name", "")).lower() == lowered:
                return bool(row.get("enabled", True)) and row.get("install_status", "installed") == "installed"
        return True
    except Exception:
        logger.warning("skill availability check failed for user=%s skill=%s; denying (fail-closed)", user_id, skill, exc_info=True)
        return False


def _admin_allowed(entry, user_id: int | None) -> bool:
    if getattr(entry, "toolset", "") == "admin" or getattr(entry, "danger", False):
        return is_admin(user_id)
    return True


def _enabled_names(enabled_tools="all") -> set[str] | None:
    value = enabled_tools
    if value is None or value == "all":
        value = os.getenv("ENABLED_TOOLS", "").strip()
        if not value:
            return None
    if isinstance(value, str):
        names = {item.strip().lower() for item in value.replace(";", ",").split(",") if item.strip()}
    elif isinstance(value, Iterable):
        names = {str(item).strip().lower() for item in value if str(item).strip()}
    else:
        names = {str(value).strip().lower()}
    return None if "all" in names else names


def _selected(entry: ToolEntry, enabled: set[str] | None) -> bool:
    if enabled is None:
        return True
    candidates = {entry.name.lower(), entry.toolset.lower()}
    if entry.skill:
        candidates.add(entry.skill.lower())
    return bool(candidates & enabled)


def _visible(user_id: int | None, enabled_tools="all") -> list[ToolEntry]:
    enabled = _enabled_names(enabled_tools)
    return [
        entry for entry in registry.all()
        if check_available(entry)
        and _user_enabled(user_id, entry.skill)
        and _admin_allowed(entry, user_id)
        and _selected(entry, enabled)
    ]


def get_all_tools(enabled_tools="all", *, user_id: int | None = None) -> list[dict]:
    _ensure_discovered()
    return [entry.schema() for entry in _visible(user_id, enabled_tools)]


async def process_tool_calls(user_id, tool_calls, enabled_tools="all", event_callback=None):
    _ensure_discovered()
    from .core.execute import execute_tool_calls
    visible = {entry.name: entry for entry in _visible(user_id, enabled_tools)}
    return await execute_tool_calls(user_id, tool_calls, event_callback=event_callback, build_context=_default_context, visible=visible)


def _skill_instructions(user_id: int | None, seen: set[str], enabled: set[str] | None) -> list[str]:
    """Prompt-only skills visible to the user contribute their body to the system prompt."""
    out: list[str] = []
    try:
        from infrastructure.tools.skills.manager import get_skill_manager
        manager = get_skill_manager()
        if user_id is None:
            manifests = manager.list_manifests()
        else:
            from infrastructure.tools.skills.user_state import is_visible_for_user
            manifests = [m for m in manager.list_manifests(user_id) if is_visible_for_user(user_id, m)]
        for manifest in manifests:
            if enabled is not None and manifest.name.lower() not in enabled and "skills" not in enabled:
                continue
            if manifest.name in seen:
                continue
            instruction = manager.get_instruction(manifest.name)
            if instruction.strip():
                out.append(instruction)
                seen.add(manifest.name)
    except Exception:
        logger.debug("skill instruction gather failed", exc_info=True)
    return out


async def invoke_tool(user_id: int, name: str, arguments: dict, enabled_tools="all"):
    """Run a single tool by name. Lighter than process_tool_calls for one-shot callers (HTTP API, cron)."""
    _ensure_discovered()
    from .core.availability import check_available
    from .core.execute import invoke_entry
    from .core.schema import validate

    entry = registry.get(name)
    if (
        entry is None
        or not check_available(entry)
        or not _user_enabled(user_id, entry.skill)
        or not _admin_allowed(entry, user_id)
        or not _selected(entry, _enabled_names(enabled_tools))
    ):
        return ToolResult.error("unknown_tool", f"Tool '{name}' is not available.")
    if getattr(entry, "raw_args", False):
        args = arguments or {}
    else:
        args, err = validate(entry.handler, arguments or {})
        if err:
            return ToolResult.error("invalid_arguments", err, name=name)
    ctx = _default_context(user_id)
    try:
        return await invoke_entry(entry, ctx, args)
    except Exception as exc:
        logger.exception("[user=%d] tool %s failed", user_id, name)
        return ToolResult.error("execution_failed", f"Tool execution failed: {exc}", exception_type=type(exc).__name__)


def get_tool_instructions(enabled_tools="all", *, user_id: int | None = None) -> str:
    _ensure_discovered()
    parts: list[str] = []
    seen: set[str] = set()
    enabled = _enabled_names(enabled_tools)
    for entry in _visible(user_id, enabled_tools):
        if entry.instruction and (entry.skill or entry.name) not in seen:
            seen.add(entry.skill or entry.name)
            parts.append(entry.instruction)
    parts.extend(_skill_instructions(user_id, seen, enabled))
    return "".join(parts)
