"""Plugin system — discover, install, and manage AI tool plugins."""

from .commands import dispatch_skill_command
from .discover import discover_manifests
from .installer import install_from_github, install_from_local, uninstall, list_installed
from .manager import get_plugin_manager, PluginManager
from .manifest import PluginManifest, load_manifest_from_path
from .registry import registry

__all__ = [
    "dispatch_skill_command",
    "discover_manifests",
    "install_from_github",
    "install_from_local",
    "uninstall",
    "list_installed",
    "get_plugin_manager",
    "PluginManager",
    "PluginManifest",
    "load_manifest_from_path",
    "registry",
]