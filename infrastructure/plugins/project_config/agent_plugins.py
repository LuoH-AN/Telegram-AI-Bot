"""External prompt plugin registration helpers."""

from __future__ import annotations

from pathlib import Path

from .files import is_external_skill_manifest


def register_external_skill_manifest(user_id: int, path: Path) -> str:
    if not is_external_skill_manifest(path):
        return ""
    try:
        from infrastructure.plugins.core.manager import get_plugin_manager

        manager = get_plugin_manager()
        name = manager.hot_load(path.parent)
        manager.add_user_plugin(user_id, name, source_type="external", source_ref=str(path))
        return f" Registered external plugin `{name}` for this user."
    except Exception as exc:
        return f" Saved plugin file, but runtime registration failed: {exc}"


def unregister_external_skill_manifest(user_id: int, path: Path) -> str:
    if not is_external_skill_manifest(path):
        return ""
    try:
        from infrastructure.plugins.core.manager import get_plugin_manager
        from infrastructure.plugins.core.manifest import load_manifest_from_path

        manifest = load_manifest_from_path(path.parent, is_builtin=False)
        if not manifest:
            return ""
        manager = get_plugin_manager()
        manager.remove_user_plugin(user_id, manifest.name)
        manager.unregister(manifest.name)
        return f" Unregistered external plugin `{manifest.name}` for this user."
    except Exception as exc:
        return f" Deleted plugin file, but runtime unregister failed: {exc}"
