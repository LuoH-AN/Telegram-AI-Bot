"""Plugin manager — discovers, loads, and manages all plugins."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any

from .discover import discover_manifests
from .manifest import PluginManifest, load_manifest_from_path
from .registry import registry

logger = logging.getLogger(__name__)

# Paths searched for built-in plugins (relative to project root)
BUILTIN_PLUGIN_ROOTS = [
    Path(__file__).parent.parent.parent / "tools",
]
# Paths searched for external plugins
EXTERNAL_PLUGIN_DIR = Path(os.getenv("PLUGIN_DIR", "runtime/plugins"))

# Tools that are built-in and always available (registered before discovery)
_BUILTIN_TOOL_NAMES = {
    "terminal",
    "sosearch",
    "scrapling",
    "project_config",
    "quick_deploy",
    "s3",
}


class PluginLoadError(Exception):
    pass


def _load_plugin_from_entry_point(manifest: PluginManifest) -> Any:
    """Import the entry_point string (e.g. 'tools.terminal.tool:TerminalTool') and return the class."""
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
    """Discovers and manages all plugins."""

    def __init__(self):
        self._discovered: dict[str, PluginManifest] = {}
        self._loaded: dict[str, Any] = {}  # name -> instance
        self._initialized = False

    def discover(self) -> None:
        """Scan all plugin directories and register their tools. Idempotent and reentrant-safe."""
        if self._initialized:
            return
        self._initialized = True  # Set before running to prevent re-entry
        manifests: list[tuple[PluginManifest, Path]] = []

        # Scan built-in roots
        for root in BUILTIN_PLUGIN_ROOTS:
            if not root.is_dir():
                continue
            for manifest_path in discover_manifests(root):
                manifest = load_manifest_from_path(manifest_path.parent, is_builtin=True)
                if manifest:
                    manifests.append((manifest, manifest_path.parent))

        # Scan external plugin directory
        external_root = EXTERNAL_PLUGIN_DIR
        if external_root.is_dir():
            for manifest_path in discover_manifests(external_root):
                manifest = load_manifest_from_path(manifest_path.parent, is_builtin=False)
                if manifest:
                    manifests.append((manifest, manifest_path.parent))

        # Load and register each plugin
        registered_names: set[str] = set()
        for manifest, plugin_path in manifests:
            try:
                cls = _load_plugin_from_entry_point(manifest)
                instance = cls()
                registry.register(instance)
                self._discovered[manifest.name] = manifest
                self._loaded[manifest.name] = instance
                registered_names.add(manifest.name.lower())
                logger.info("Loaded plugin: %s @ %s", manifest.name, plugin_path)
            except PluginLoadError as exc:
                logger.warning("Failed to load plugin '%s' from %s: %s", manifest.name, plugin_path, exc)
            except Exception:
                logger.exception("Unexpected error loading plugin '%s' from %s", manifest.name, plugin_path)

        # Mark built-in tools as enabled by default
        for name in _BUILTIN_TOOL_NAMES:
            registry.enable(name)

        self._initialized = True
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


# Singleton
_manager = PluginManager()


def get_plugin_manager() -> PluginManager:
    if not _manager._initialized:
        _manager.discover()
    return _manager
