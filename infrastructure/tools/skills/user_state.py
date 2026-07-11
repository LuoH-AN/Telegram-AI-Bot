"""Per-user skill enable/visibility state, backed by the cache + DB skill tables."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from infrastructure.cache import cache, sync_to_database

from .manifest import SkillManifest


def _mutation_snapshot(user_id: int) -> tuple[bool, list[dict], list, list, list]:
    with cache._lock:
        return (
            user_id in cache._skills_cache,
            deepcopy(cache._skills_cache.get(user_id, [])),
            [item for item in cache._new_skills if item.get("user_id") == user_id],
            [item for item in cache._updated_skills if item.get("user_id") == user_id],
            [item for item in cache._deleted_skills if item[0] == user_id],
        )


def _restore_mutation(user_id: int, snapshot: tuple[bool, list[dict], list, list, list]) -> None:
    existed, skills, new_skills, updated_skills, deleted_skills = snapshot
    with cache._lock:
        if existed:
            cache._skills_cache[user_id] = skills
        else:
            cache._skills_cache.pop(user_id, None)
        cache._new_skills = [item for item in cache._new_skills if item.get("user_id") != user_id] + new_skills
        cache._updated_skills = [item for item in cache._updated_skills if item.get("user_id") != user_id] + updated_skills
        cache._deleted_skills = [item for item in cache._deleted_skills if item[0] != user_id] + deleted_skills


def _find_user_skill(user_id: int, name: str) -> dict | None:
    lowered = name.lower()
    for skill in cache.get_skills(user_id):
        if str(skill.get("name", "")).lower() == lowered:
            return skill
    return None


def _manifest_json(manifest: SkillManifest) -> dict:
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


def is_visible_for_user(user_id: int, manifest: SkillManifest) -> bool:
    if manifest.is_builtin:
        return True
    skill = _find_user_skill(user_id, manifest.name)
    return bool(skill and skill.get("install_status", "installed") == "installed")


def is_enabled_for_user(user_id: int | None, manifest: SkillManifest | None, name: str) -> bool:
    if user_id is None:
        return True
    skill = _find_user_skill(user_id, name)
    if skill is not None:
        return bool(skill.get("enabled", True)) and skill.get("install_status", "installed") == "installed"
    return bool(manifest and manifest.is_builtin)


def ensure_user_skill(
    user_id: int,
    manifest: SkillManifest,
    *,
    enabled: bool | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    sync: bool = True,
) -> dict:
    snapshot = _mutation_snapshot(user_id) if sync else None
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
        try:
            sync_to_database()
        except Exception:
            _restore_mutation(user_id, snapshot)
            raise
    return skill


def set_user_skill_enabled(user_id: int, manifest: SkillManifest, enabled: bool) -> None:
    ensure_user_skill(user_id, manifest, enabled=enabled, sync=True)


def remove_user_skill(user_id: int, manifest: SkillManifest) -> None:
    if manifest.is_builtin:
        set_user_skill_enabled(user_id, manifest, False)
        return
    existing = _find_user_skill(user_id, manifest.name)
    if existing:
        snapshot = _mutation_snapshot(user_id)
        cache.delete_skill(user_id, existing["name"])
        try:
            sync_to_database()
        except Exception:
            _restore_mutation(user_id, snapshot)
            raise


def any_user_has_skill(name: str) -> bool:
    lowered = name.lower()
    for skills in getattr(cache, "_skills_cache", {}).values():
        for skill in skills:
            if str(skill.get("name", "")).lower() == lowered and skill.get("install_status", "installed") == "installed":
                return True
    return False


def visible_manifests(user_id: int, manifests: Iterable[SkillManifest]) -> list[SkillManifest]:
    return [m for m in manifests if is_visible_for_user(user_id, m)]
