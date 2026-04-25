"""Compatibility shim: make tools.core.registry.registry point to the PluginRegistry.

This ensures that any remaining code doing:
    from tools.core.registry import registry
continues to work and uses the shared PluginRegistry singleton.
"""

from core.plugins import registry

# Also re-export the class for type-checkers / anyone subclassing
from core.plugins.registry import PluginRegistry as ToolRegistry

__all__ = ["registry", "ToolRegistry"]
