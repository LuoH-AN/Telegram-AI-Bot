"""Per-user plugin state backed by the cache/database skill tables."""

from __future__ import annotations

from typing import Iterable

from cache import cache, sync_to_database

from .manifest import PluginManifest


def _find_user_skill(user_id: int, name: str) -> dict | None:
    lowered = name.lower()
    for skill in cache.get_skills(user_id):
        if str(skill.get("name", "")).lower() == lowered:
            return skill
    return None


def _manifest_json(manifest: PluginManifest) -> dict:
    return {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "repository": manifest.repository,
        "entry_point": manifest.entry_point,
        "capabilities": manifest.capabilities,
        "platforms": manifest.platforms,
        "source_path": manifest.source_path,
    }


def is_visible_for_user(user_id: int, manifest: PluginManifest) -> bool:
    if manifest.is_builtin:
        return True
    skill = _find_user_skill(user_id, manifest.name)
    return bool(skill and skill.get("install_status", "installed") == "installed")


def is_enabled_for_user(user_id: int | None, manifest: PluginManifest | None, name: str) -> bool:
    if user_id is None:
        return True
    skill = _find_user_skill(user_id, name)
    if skill is not None:
        return bool(skill.get("enabled", True)) and skill.get("install_status", "installed") == "installed"
    return bool(manifest and manifest.is_builtin)


def ensure_user_skill(
    user_id: int,
    manifest: PluginManifest,
    *,
    enabled: bool | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    sync: bool = True,
) -> dict:
    existing = _find_user_skill(user_id, manifest.name)
    final_enabled = bool(existing.get("enabled", True)) if existing and enabled is None else (True if enabled is None else enabled)
    data = {
        "name": manifest.name,
        "display_name": manifest.name,
        "source_type": source_type or ("builtin" if manifest.is_builtin else "external"),
        "source_ref": source_ref or manifest.repository or manifest.source_path,
        "version": manifest.version,
        "enabled": bool(final_enabled),
        "install_status": "installed",
        "entrypoint": manifest.entry_point,
        "manifest": _manifest_json(manifest),
        "capabilities": list(manifest.capabilities),
        "persist_mode": "db",
        "last_error": "",
    }
    if existing:
        update_data = dict(data)
        update_data.pop("name", None)
        cache.update_skill(user_id, existing["name"], **update_data)
        skill = _find_user_skill(user_id, manifest.name) or existing
    else:
        skill = cache.add_skill(user_id, **data) or data
    if sync:
        sync_to_database()
    return skill


def set_user_skill_enabled(user_id: int, manifest: PluginManifest, enabled: bool) -> None:
    ensure_user_skill(user_id, manifest, enabled=enabled, sync=True)


def remove_user_skill(user_id: int, manifest: PluginManifest) -> None:
    if manifest.is_builtin:
        set_user_skill_enabled(user_id, manifest, False)
        return
    existing = _find_user_skill(user_id, manifest.name)
    if existing:
        cache.delete_skill(user_id, existing["name"])
        sync_to_database()


def any_user_has_skill(name: str) -> bool:
    lowered = name.lower()
    for skills in getattr(cache, "_skills_cache", {}).values():
        for skill in skills:
            if (
                str(skill.get("name", "")).lower() == lowered
                and skill.get("install_status", "installed") == "installed"
            ):
                return True
    return False


def visible_manifests(user_id: int, manifests: Iterable[PluginManifest]) -> list[PluginManifest]:
    return [manifest for manifest in manifests if is_visible_for_user(user_id, manifest)]
