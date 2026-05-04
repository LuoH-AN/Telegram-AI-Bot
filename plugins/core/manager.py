"""Plugin manager — discovers, loads, and manages all plugins."""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Any

from .discover import discover_manifests
from .manifest import PluginManifest, load_manifest_from_path
from .registry import registry
from .skill_plugin import SkillPlugin

logger = logging.getLogger(__name__)

BUILTIN_PLUGIN_ROOTS = [Path(__file__).parent.parent]
EXTERNAL_PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "runtime/plugins"))


class PluginLoadError(Exception):
    pass


def _instantiate(manifest: PluginManifest) -> Any:
    if not manifest.entry_point:
        return SkillPlugin(manifest)
    if ":" not in manifest.entry_point:
        raise PluginLoadError(f"entry_point '{manifest.entry_point}' must contain ':'")
    module_path, class_name = manifest.entry_point.rsplit(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise PluginLoadError(f"Failed to import '{module_path}': {exc}") from exc
    cls = getattr(module, class_name, None)
    if cls is None:
        raise PluginLoadError(f"Module '{module_path}' has no class '{class_name}'")
    return cls()


class PluginManager:
    def __init__(self):
        self._discovered: dict[str, PluginManifest] = {}
        self._loaded: dict[str, Any] = {}
        self._initialized = False

    def _collect(self) -> list[tuple[PluginManifest, Path]]:
        out: list[tuple[PluginManifest, Path]] = []
        for root in BUILTIN_PLUGIN_ROOTS:
            if not root.is_dir():
                continue
            for skill_path in discover_manifests(root):
                if "plugins/core" in str(skill_path):
                    continue
                m = load_manifest_from_path(skill_path.parent, is_builtin=True)
                if m:
                    out.append((m, skill_path.parent))
        if EXTERNAL_PLUGIN_DIR.is_dir():
            for skill_path in discover_manifests(EXTERNAL_PLUGIN_DIR):
                m = load_manifest_from_path(skill_path.parent, is_builtin=False)
                if m:
                    out.append((m, skill_path.parent))
        return out

    def _register(self, manifest: PluginManifest) -> None:
        instance = _instantiate(manifest)
        registry.register(instance)
        self._discovered[manifest.name] = manifest
        self._loaded[manifest.name] = instance

    def discover(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        for manifest, plugin_path in self._collect():
            try:
                self._register(manifest)
                logger.info("Loaded plugin: %s @ %s", manifest.name, plugin_path)
            except PluginLoadError as exc:
                logger.warning("Failed to load '%s' from %s: %s", manifest.name, plugin_path, exc)
            except Exception:
                logger.exception("Unexpected error loading '%s' from %s", manifest.name, plugin_path)
        logger.info("Plugin discovery complete: %d loaded (%s)", len(self._discovered), ", ".join(self._discovered.keys()))

    def hot_load(self, plugin_dir: Path) -> str:
        manifest = load_manifest_from_path(plugin_dir, is_builtin=False)
        if not manifest:
            raise PluginLoadError(f"No SKILL.md in {plugin_dir}")
        self._register(manifest)
        logger.info("Hot-loaded plugin: %s", manifest.name)
        return manifest.name

    def list_plugins(self) -> list[PluginManifest]:
        return list(self._discovered.values())

    def get_plugin(self, name: str) -> Any | None:
        return self._loaded.get(name) or self._loaded.get(name.lower())

    def is_enabled(self, name: str) -> bool:
        return registry.is_enabled(name)

    def enable(self, name: str) -> bool:
        return registry.enable(name)

    def disable(self, name: str) -> bool:
        return registry.disable(name)

    @property
    def initialized(self) -> bool:
        return self._initialized


_manager = PluginManager()


def get_plugin_manager() -> PluginManager:
    if not _manager._initialized:
        _manager.discover()
    return _manager
