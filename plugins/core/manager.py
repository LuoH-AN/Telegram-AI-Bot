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

logger = logging.getLogger(__name__)

# Paths searched for built-in plugins (relative to project root)
BUILTIN_PLUGIN_ROOTS = [
    Path(__file__).parent.parent,  # plugins/
]

# Paths searched for external plugins
EXTERNAL_PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "runtime/plugins"))


class PluginLoadError(Exception):
    pass


def _load_plugin_from_entry_point(manifest: PluginManifest) -> Any:
    if ":" not in manifest.entry_point:
        raise PluginLoadError(f"entry_point '{manifest.entry_point}' must contain ':' separating module from class")

    module_path, class_name = manifest.entry_point.rsplit(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise PluginLoadError(f"Failed to import module '{module_path}': {exc}") from exc

    cls = getattr(module, class_name, None)
    if cls is None:
        raise PluginLoadError(f"Module '{module_path}' has no class '{class_name}'")
    return cls


class PluginManager:
    def __init__(self):
        self._discovered: dict[str, PluginManifest] = {}
        self._loaded: dict[str, Any] = {}
        self._initialized = False

    def discover(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        manifests: list[tuple[PluginManifest, Path]] = []

        for root in BUILTIN_PLUGIN_ROOTS:
            if not root.is_dir():
                continue
            for manifest_path in discover_manifests(root):
                # Skip core/ (it's the framework, not a plugin)
                if "plugins/core" in str(manifest_path):
                    continue
                manifest = load_manifest_from_path(manifest_path.parent, is_builtin=True)
                if manifest:
                    manifests.append((manifest, manifest_path.parent))

        external_root = EXTERNAL_PLUGIN_DIR
        if external_root.is_dir():
            for manifest_path in discover_manifests(external_root):
                manifest = load_manifest_from_path(manifest_path.parent, is_builtin=False)
                if manifest:
                    manifests.append((manifest, manifest_path.parent))

        for manifest, plugin_path in manifests:
            try:
                cls = _load_plugin_from_entry_point(manifest)
                instance = cls()
                registry.register(instance)
                self._discovered[manifest.name] = manifest
                self._loaded[manifest.name] = instance
                logger.info("Loaded plugin: %s @ %s", manifest.name, plugin_path)
            except PluginLoadError as exc:
                logger.warning("Failed to load plugin '%s' from %s: %s", manifest.name, plugin_path, exc)
            except Exception:
                logger.exception("Unexpected error loading plugin '%s' from %s", manifest.name, plugin_path)

        logger.info("Plugin discovery complete: %d plugins loaded (%s)", len(self._discovered), ", ".join(self._discovered.keys()))

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
