"""Handlers for /skill subcommands."""

from __future__ import annotations

import logging

from .installer import install_from_github, install_from_local, uninstall
from .manager import get_plugin_manager

logger = logging.getLogger(__name__)


async def handle_skill_list(ctx) -> str:
    """List all discovered plugins with their status."""
    manager = get_plugin_manager()
    plugins = manager.list_plugins()

    if not plugins:
        return "No plugins discovered."

    lines = ["Available plugins:"]
    for p in sorted(plugins, key=lambda x: x.name):
        status = "enabled" if manager.is_enabled(p.name) else "disabled"
        builtin = " [builtin]" if p.is_builtin else ""
        lines.append(f"  • {p.name} {p.version} ({status}){builtin}")
        if p.description:
            lines.append(f"    {p.description}")

    return "\n".join(lines)


async def handle_skill_install(ctx, source: str) -> str:
    """Install a plugin from GitHub URL or local path."""
    source = source.strip()
    if not source:
        return "Usage: /skill install <github-url-or-owner/repo>"

    if source.startswith("http") or "/" in source:
        result = install_from_github(source)
    else:
        result = install_from_local(source)

    if not result.get("ok"):
        return f"Install failed: {result.get('message', 'unknown error')}"

    name = result.get("name")
    # Trigger re-discovery to pick up newly installed plugin
    manager = get_plugin_manager()
    if not manager.initialized:
        manager.discover()
    else:
        # Re-load just this plugin
        from .discover import discover_manifests
        from .manifest import load_manifest_from_path
        from pathlib import Path
        from core.plugins.manager import PLUGIN_DIR, _load_plugin_from_entry_point

        plugin_dir = Path(result.get("path", PLUGIN_DIR / name))
        manifest = load_manifest_from_path(plugin_dir, is_builtin=False)
        if manifest:
            try:
                cls = _load_plugin_from_entry_point(manifest)
                instance = cls()
                from core.plugins.registry import registry
                registry.register(instance)
                manager._discovered[manifest.name] = manifest
                manager._loaded[manifest.name] = instance
                logger.info("Hot-loaded plugin: %s", manifest.name)
            except Exception as exc:
                logger.warning("Failed to hot-load plugin '%s': %s", name, exc)
                return f"Installed but failed to load: {exc}"

    return f"Plugin '{name}' installed successfully."


async def handle_skill_remove(ctx, name: str) -> str:
    """Uninstall a plugin."""
    name = name.strip()
    if not name:
        return "Usage: /skill remove <name>"

    result = uninstall(name)
    if not result.get("ok"):
        return f"Remove failed: {result.get('message', 'unknown error')}"

    # Disable it in the registry
    manager = get_plugin_manager()
    manager.disable(name)
    return f"Plugin '{name}' uninstalled."


async def handle_skill_enable(ctx, name: str, enable: bool = True) -> str:
    """Enable or disable a plugin."""
    name = name.strip()
    if not name:
        return "Usage: /skill enable <name>"

    manager = get_plugin_manager()
    action = "enable" if enable else "disable"
    ok = manager.enable(name) if enable else manager.disable(name)

    if not ok:
        return f"Plugin '{name}' not found."
    return f"Plugin '{name}' {action}d."


async def handle_skill_info(ctx, name: str) -> str:
    """Show detailed info about a plugin."""
    name = name.strip()
    if not name:
        return "Usage: /skill info <name>"

    manager = get_plugin_manager()
    plugin = None
    for p in manager.list_plugins():
        if p.name.lower() == name.lower():
            plugin = p
            break

    if not plugin:
        return f"Plugin '{name}' not found."

    status = "enabled" if manager.is_enabled(plugin.name) else "disabled"
    lines = [
        f"Plugin: {plugin.name}",
        f"Version: {plugin.version}",
        f"Status: {status}",
        f"Description: {plugin.description or 'N/A'}",
        f"Author: {plugin.author or 'N/A'}",
        f"Repository: {plugin.repository or 'N/A'}",
        f"Entry point: {plugin.entry_point}",
        f"Capabilities: {', '.join(plugin.capabilities) or 'N/A'}",
        f"Platforms: {', '.join(plugin.platforms) or 'all'}",
        f"Builtin: {'Yes' if plugin.is_builtin else 'No'}",
        f"Source: {plugin.source_path}",
    ]
    return "\n".join(lines)


async def dispatch_skill_command(ctx, args: list[str]) -> str:
    """Main dispatcher for /skill subcommands."""
    if not args:
        return "Usage: /skill <list|install|remove|enable|disable|info> [args]"

    sub = args[0].lower()
    rest = args[1:]

    if sub == "list":
        return await handle_skill_list(ctx)
    elif sub == "install":
        source = rest[0] if rest else ""
        return await handle_skill_install(ctx, source)
    elif sub == "remove":
        name = rest[0] if rest else ""
        return await handle_skill_remove(ctx, name)
    elif sub == "enable":
        name = rest[0] if rest else ""
        return await handle_skill_enable(ctx, name, enable=True)
    elif sub == "disable":
        name = rest[0] if rest else ""
        return await handle_skill_enable(ctx, name, enable=False)
    elif sub == "info":
        name = rest[0] if rest else ""
        return await handle_skill_info(ctx, name)
    else:
        return f"Unknown subcommand: {sub}. Use: list, install, remove, enable, disable, info."
