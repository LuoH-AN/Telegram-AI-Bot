"""Skill manager — discover, load, hot-load, and manage per-user skill state.

Replaces infrastructure.plugins.core.manager. Uses the new SkillManifest (real
YAML) and tracks prompt-only skills separately from native @tool functions.
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Any

from .discover import discover_skill_dirs
from .manifest import SkillManifest, load_manifest

logger = logging.getLogger(__name__)

BUILTIN_SKILL_ROOTS = [Path(__file__).resolve().parent / "builtin"]
EXTERNAL_SKILL_DIR = Path(os.getenv("PLUGIN_DIR", "/data/plugins"))


class SkillLoadError(Exception):
    pass


def _load_skill_body(manifest: SkillManifest) -> str:
    """Instruction text a prompt-only skill contributes to the system prompt."""
    from pathlib import Path

    lines = [f"\n## Skill: {manifest.name}"]
    if manifest.description:
        lines.append(manifest.description)
    scripts_dir = Path(manifest.source_path) / "scripts"
    if scripts_dir.is_dir():
        scripts = [f.name for f in scripts_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        if scripts:
            lines.append(f"Scripts directory: {scripts_dir}")
            lines.append("Invoke via terminal tool, e.g.:")
            for script in scripts[:3]:
                lines.append(f'  {{"action":"exec","command":"python3 {scripts_dir}/{script} <args>"}}')
    lines.append("")
    return "\n".join(lines) + manifest.body + "\n"


class SkillRecord:
    """A loaded skill: manifest + optional instruction text."""

    def __init__(self, manifest: SkillManifest):
        self.manifest = manifest
        self._instruction: str | None = None

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def instruction(self) -> str:
        if self._instruction is None:
            self._instruction = _load_skill_body(self.manifest)
        return self._instruction


class SkillManager:
    def __init__(self) -> None:
        self._records: dict[str, SkillRecord] = {}
        self._initialized = False

    def _collect(self) -> list[SkillManifest]:
        manifests: list[SkillManifest] = []
        for root in BUILTIN_SKILL_ROOTS:
            if not root.is_dir():
                continue
            for skill_path in discover_skill_dirs(root):
                manifest = load_manifest(skill_path.parent, is_builtin=True)
                if manifest:
                    manifests.append(manifest)
        if EXTERNAL_SKILL_DIR.is_dir():
            for skill_path in discover_skill_dirs(EXTERNAL_SKILL_DIR):
                manifest = load_manifest(skill_path.parent, is_builtin=False)
                if manifest:
                    manifests.append(manifest)
        return manifests

    def discover(self) -> None:
        if self._initialized:
            return
        for manifest in self._collect():
            self._records[manifest.name] = SkillRecord(manifest)
            logger.info("Loaded skill: %s", manifest.name)
        self._initialized = True
        logger.info("Skill discovery complete: %d loaded (%s)", len(self._records), ", ".join(self._records))

    def hot_load(self, skill_dir: Path) -> str:
        manifest = load_manifest(skill_dir, is_builtin=False)
        if not manifest:
            raise SkillLoadError(f"No SKILL.md in {skill_dir}")
        self._records[manifest.name] = SkillRecord(manifest)
        logger.info("Hot-loaded skill: %s", manifest.name)
        return manifest.name

    def unregister(self, name: str) -> bool:
        return self._records.pop(name, None) is not None

    def list_manifests(self, user_id: int | None = None) -> list[SkillManifest]:
        self.discover()
        manifests = list(r.manifest for r in self._records.values())
        if user_id is None:
            return manifests
        from .user_state import visible_manifests

        return visible_manifests(user_id, manifests)

    def get_manifest(self, name: str) -> SkillManifest | None:
        self.discover()
        record = self._records.get(name)
        return record.manifest if record else None

    def get_instruction(self, name: str) -> str:
        self.discover()
        record = self._records.get(name)
        return record.instruction if record else ""

    def is_enabled(self, name: str, user_id: int | None = None) -> bool:
        from .user_state import is_enabled_for_user

        manifest = self.get_manifest(name)
        return bool(manifest and is_enabled_for_user(user_id, manifest, name))

    def set_user_enabled(self, user_id: int, name: str, enabled: bool) -> bool:
        manifest = self.get_manifest(name)
        if not manifest:
            return False
        from .user_state import set_user_skill_enabled

        set_user_skill_enabled(user_id, manifest, enabled)
        return True

    def add_user_skill(self, user_id: int, name: str, *, source_type: str = "external", source_ref: str = "") -> bool:
        manifest = self.get_manifest(name)
        if not manifest:
            return False
        from .user_state import ensure_user_skill

        ensure_user_skill(user_id, manifest, enabled=True, source_type=source_type, source_ref=source_ref)
        return True

    def remove_user_skill(self, user_id: int, name: str) -> bool:
        manifest = self.get_manifest(name)
        if not manifest:
            return False
        from .user_state import remove_user_skill

        remove_user_skill(user_id, manifest)
        return True

    @property
    def initialized(self) -> bool:
        return self._initialized


_manager: SkillManager | None = None


def get_skill_manager() -> SkillManager:
    global _manager
    if _manager is None:
        _manager = SkillManager()
    _manager.discover()
    return _manager
