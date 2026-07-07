"""External skill registration helpers — hot-load/remove runtime/plugins SKILL.md."""

from __future__ import annotations

from pathlib import Path

from .manager import get_skill_manager
from .manifest import load_manifest


def register_external_skill_manifest(user_id: int, path: Path) -> str:
    """Called after writing a runtime/plugins/<name>/SKILL.md: hot-load + register for user."""
    from infrastructure.tools.admin.files import is_external_skill_manifest as _is_ext

    if not _is_ext(path):
        return ""
    try:
        manager = get_skill_manager()
        name = manager.hot_load(path.parent)
        manager.add_user_skill(user_id, name, source_type="external", source_ref=str(path))
        return f" Registered external skill `{name}` for this user."
    except Exception as exc:
        return f" Saved skill file, but runtime registration failed: {exc}"


def unregister_external_skill_manifest(user_id: int, path: Path) -> str:
    from infrastructure.tools.admin.files import is_external_skill_manifest as _is_ext
    if not _is_ext(path):
        return ""
    try:
        manifest = load_manifest(path.parent, is_builtin=False)
        if not manifest:
            return ""
        manager = get_skill_manager()
        manager.remove_user_skill(user_id, manifest.name)
        manager.unregister(manifest.name)
        return f" Unregistered external skill `{manifest.name}` for this user."
    except Exception as exc:
        return f" Deleted skill file, but runtime unregister failed: {exc}"
