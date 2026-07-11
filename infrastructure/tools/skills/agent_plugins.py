"""External skill registration helpers — hot-load/remove runtime/plugins SKILL.md."""

from __future__ import annotations

from pathlib import Path

from .manager import get_skill_manager
from .manifest import load_manifest


def register_external_skill_manifest(user_id: int, path: Path) -> str:
    """Called after writing a runtime/plugins/<name>/SKILL.md: hot-load + register for user."""
    from infrastructure.tools.builtin.config_file.files import is_external_skill_manifest as _is_ext

    if not _is_ext(path):
        return ""
    manifest = load_manifest(path.parent, is_builtin=False)
    if not manifest:
        raise ValueError(f"Invalid SKILL.md: {path}")
    manager = get_skill_manager()
    previous = manager.snapshot_record(manifest.name)
    try:
        name = manager.hot_load(path.parent)
        if not manager.add_user_skill(user_id, name, source_type="external", source_ref=str(path)):
            raise RuntimeError(f"Skill '{name}' was loaded but could not be registered for the user")
        return f" Registered external skill `{name}` for this user."
    except Exception:
        manager.restore_record(manifest.name, previous)
        raise


def unregister_external_skill_manifest(user_id: int, path: Path) -> str:
    from infrastructure.tools.builtin.config_file.files import is_external_skill_manifest as _is_ext
    if not _is_ext(path):
        return ""
    manifest = load_manifest(path.parent, is_builtin=False)
    if not manifest:
        return ""
    manager = get_skill_manager()
    previous = manager.snapshot_record(manifest.name)
    try:
        manager.remove_user_skill(user_id, manifest.name)
        manager.unregister(manifest.name)
        return f" Unregistered external skill `{manifest.name}` for this user."
    except Exception:
        manager.restore_record(manifest.name, previous)
        raise
