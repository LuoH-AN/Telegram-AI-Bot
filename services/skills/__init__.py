"""Skill management — now backed by the plugin system."""

from __future__ import annotations

import logging

from core.plugins import (
    dispatch_skill_command,
    get_plugin_manager,
    install_from_github,
    install_from_local,
    list_installed,
    registry,
    uninstall,
)

logger = logging.getLogger(__name__)


def list_skills(user_id: int) -> list[dict]:
    """List all plugins visible to this user."""
    del user_id
    plugins = get_plugin_manager().list_plugins()
    manager = get_plugin_manager()
    return [
        {
            "name": p.name,
            "display_name": p.name,
            "version": p.version,
            "description": p.description,
            "enabled": manager.is_enabled(p.name),
            "is_builtin": p.is_builtin,
            "source": p.source_path,
        }
        for p in plugins
    ]


def get_skill(user_id: int, name: str) -> dict | None:
    """Get a specific plugin by name."""
    del user_id
    manager = get_plugin_manager()
    plugin = manager.get_plugin(name)
    if not plugin:
        return None
    manifest = None
    for p in manager.list_plugins():
        if p.name.lower() == name.lower():
            manifest = p
            break
    if manifest:
        return {
            "name": manifest.name,
            "display_name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "enabled": manager.is_enabled(manifest.name),
            "is_builtin": manifest.is_builtin,
            "source": manifest.source_path,
        }
    return None


def install_skill(
    user_id: int,
    name: str,
    *,
    source_type: str = "builtin",
    source_ref: str = "",
    persist_mode: str = "none",
) -> dict:
    """Install a skill (now an alias for plugin install)."""
    del user_id, persist_mode
    if source_type == "github":
        return install_from_github(source_ref, name_hint=name)
    elif source_type == "local":
        return install_from_local(source_ref)
    else:
        return {"ok": False, "message": f"Unknown source_type '{source_type}' for install_skill"}


def install_skill_from_github(user_id: int, github_url: str, *, name_hint: str = "", persist_mode: str = "none") -> dict | None:
    del user_id, persist_mode
    return install_from_github(github_url, name_hint=name_hint)


def enable_skill(user_id: int, name: str, enabled: bool = True) -> bool:
    """Enable or disable a plugin."""
    del user_id
    manager = get_plugin_manager()
    return manager.enable(name) if enabled else manager.disable(name)


def remove_skill(user_id: int, name: str) -> bool:
    del user_id
    result = uninstall(name)
    return result.get("ok", False)


def call_skill(user_id: int, name: str, input_text: str) -> str:
    """Call a skill directly (for chat-based skill invocation)."""
    del user_id
    plugin = get_plugin_manager().get_plugin(name)
    if not plugin:
        return f"Skill '{name}' not found."
    try:
        result = plugin.execute(user_id=0, tool_name=name, arguments={"input": input_text})
        return result or "(OK)"
    except Exception as exc:
        return f"Error: {exc}"


def persist_skill_state(user_id: int, name: str) -> bool:
    """Persist skill state to database (placeholder for now)."""
    del user_id, name
    return False


def persist_skill_snapshot(user_id: int, name: str, snapshot_id: str | None = None) -> bool:
    del user_id, name, snapshot_id
    return False


def list_skill_snapshots(user_id: int, name: str) -> list[str]:
    del user_id, name
    return []


def restore_skill(user_id: int, name: str) -> bool:
    del user_id, name
    return False


def restore_skill_snapshot(user_id: int, name: str, snapshot_id: str | None = None) -> bool:
    del user_id, name, snapshot_id
    return False


def auto_restore_skills(user_id: int) -> None:
    del user_id
    pass