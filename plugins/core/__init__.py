"""Plugin system core — discover, install, and manage AI tool plugins."""

from .base import BasePlugin, BaseTool
from .commands import dispatch_skill_command
from .discover import discover_manifests
from .events import ToolEventCallback, emit_tool_progress
from .installer import install_from_github, install_from_local, uninstall, list_installed
from .manager import get_plugin_manager, PluginManager
from .manifest import PluginManifest, load_manifest_from_path
from .registry import PluginRegistry, registry

__all__ = [
    "BasePlugin",
    "BaseTool",
    "dispatch_skill_command",
    "discover_manifests",
    "emit_tool_progress",
    "install_from_github",
    "install_from_local",
    "list_installed",
    "uninstall",
    "get_plugin_manager",
    "PluginManager",
    "PluginManifest",
    "PluginRegistry",
    "load_manifest_from_path",
    "registry",
    "ToolEventCallback",
]
