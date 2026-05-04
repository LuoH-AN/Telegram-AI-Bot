"""Handlers for /skill subcommands."""

from __future__ import annotations

import logging
from pathlib import Path

from .installer import PLUGIN_DIR, install_from_github, install_from_local, uninstall
from .manager import get_plugin_manager

logger = logging.getLogger(__name__)


async def handle_skill_list(ctx) -> str:
    manager = get_plugin_manager()
    plugins = manager.list_plugins()
    if not plugins:
        return "No plugins discovered."
    lines = ["Available plugins:"]
    for p in sorted(plugins, key=lambda x: x.name):
        status = "enabled" if manager.is_enabled(p.name) else "disabled"
        builtin = " [builtin]" if p.is_builtin else ""
        lines.append(f"  - {p.name} {p.version} ({status}){builtin}")
        if p.description:
            lines.append(f"    {p.description}")
    return "\n".join(lines)


async def handle_skill_install(ctx, source: str) -> str:
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
    manager = get_plugin_manager()
    if not manager.initialized:
        manager.discover()
    else:
        plugin_dir = Path(result.get("path", PLUGIN_DIR / name))
        try:
            manager.hot_load(plugin_dir)
        except Exception as exc:
            logger.warning("Failed to hot-load plugin '%s': %s", name, exc)
            return f"Installed but failed to load: {exc}"
    return f"Plugin '{name}' installed successfully."


async def handle_skill_remove(ctx, name: str) -> str:
    name = name.strip()
    if not name:
        return "Usage: /skill remove <name>"
    result = uninstall(name)
    if not result.get("ok"):
        return f"Remove failed: {result.get('message', 'unknown error')}"
    get_plugin_manager().disable(name)
    return f"Plugin '{name}' uninstalled."


async def handle_skill_enable(ctx, name: str, enable: bool = True) -> str:
    name = name.strip()
    if not name:
        return "Usage: /skill enable <name>"
    manager = get_plugin_manager()
    ok = manager.enable(name) if enable else manager.disable(name)
    if not ok:
        return f"Plugin '{name}' not found."
    return f"Plugin '{name}' {'enable' if enable else 'disable'}d."


async def handle_skill_info(ctx, name: str) -> str:
    name = name.strip()
    if not name:
        return "Usage: /skill info <name>"
    manager = get_plugin_manager()
    plugin = next((p for p in manager.list_plugins() if p.name.lower() == name.lower()), None)
    if not plugin:
        return f"Plugin '{name}' not found."
    status = "enabled" if manager.is_enabled(plugin.name) else "disabled"
    return "\n".join([
        f"Plugin: {plugin.name}",
        f"Version: {plugin.version}",
        f"Status: {status}",
        f"Description: {plugin.description or 'N/A'}",
        f"Author: {plugin.author or 'N/A'}",
        f"Repository: {plugin.repository or 'N/A'}",
        f"Entry point: {plugin.entry_point or '(prompt-only skill)'}",
        f"Capabilities: {', '.join(plugin.capabilities) or 'N/A'}",
        f"Platforms: {', '.join(plugin.platforms) or 'all'}",
        f"Builtin: {'Yes' if plugin.is_builtin else 'No'}",
        f"Source: {plugin.source_path}",
    ])


async def dispatch_skill_command(ctx, args: list[str]) -> str:
    if not args:
        return "Usage: /skill <list|install|remove|enable|disable|info> [args]"
    sub = args[0].lower()
    arg = args[1] if len(args) > 1 else ""
    if sub == "list":
        return await handle_skill_list(ctx)
    if sub == "install":
        return await handle_skill_install(ctx, arg)
    if sub == "remove":
        return await handle_skill_remove(ctx, arg)
    if sub == "enable":
        return await handle_skill_enable(ctx, arg, enable=True)
    if sub == "disable":
        return await handle_skill_enable(ctx, arg, enable=False)
    if sub == "info":
        return await handle_skill_info(ctx, arg)
    return f"Unknown subcommand: {sub}. Use: list, install, remove, enable, disable, info."
