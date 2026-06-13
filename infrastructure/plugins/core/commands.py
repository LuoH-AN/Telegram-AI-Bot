"""Handlers for /skill subcommands."""

from __future__ import annotations

import logging
from pathlib import Path

from .installer import PLUGIN_DIR, install_from_github, install_from_local, uninstall
from .manager import get_plugin_manager

logger = logging.getLogger(__name__)


def _user_id(ctx) -> int:
    return int(getattr(ctx, "session_user_id", getattr(ctx, "local_user_id", 0)))


def _find_user_plugin(manager, user_id: int, name: str):
    lowered = name.lower()
    return next((p for p in manager.list_plugins(user_id) if p.name.lower() == lowered), None)


def _install_source_type(source: str) -> str:
    if source.startswith("http") or ("/" in source and not source.startswith(("/", "./", "../")) and not Path(source).exists()):
        return "github"
    return "local"


async def handle_skill_list(ctx) -> str:
    user_id = _user_id(ctx)
    manager = get_plugin_manager()
    plugins = manager.list_plugins(user_id)
    if not plugins:
        return "📝 **No plugins available for your account.**"
    lines = ["🔌 **Your plugins:**"]
    for p in sorted(plugins, key=lambda x: x.name):
        status = "✅ enabled" if manager.is_enabled(p.name, user_id) else "❌ disabled"
        builtin = " `[builtin]`" if p.is_builtin else ""
        lines.append(f"• **{p.name}** `{p.version}` ({status}){builtin}")
        if p.description:
            lines.append(f"  _{p.description}_")
    return "\n".join(lines)


async def handle_skill_install(ctx, source: str) -> str:
    source = source.strip()
    if not source:
        return f"**Usage:** `/skill install <github-url-or-owner/repo>`"
    user_id = _user_id(ctx)
    source_type = _install_source_type(source)
    if source_type == "github":
        result = install_from_github(source)
    else:
        result = install_from_local(source)
    if not result.get("ok"):
        return f"❌ **Install failed:** {result.get('message', 'unknown error')}"
    name = result.get("name")
    manager = get_plugin_manager()
    if not manager.initialized:
        manager.discover()
    else:
        plugin_dir = Path(result.get("path", PLUGIN_DIR / name))
        try:
            name = manager.hot_load(plugin_dir)
        except Exception as exc:
            logger.warning("Failed to hot-load plugin '%s': %s", name, exc)
            return f"⚠️ **Installed but failed to load:** {exc}"
    manager.add_user_plugin(user_id, name, source_type=source_type, source_ref=source)
    return f"✅ **Plugin `{name}` installed for your account.**"


async def handle_skill_remove(ctx, name: str) -> str:
    name = name.strip()
    if not name:
        return f"**Usage:** `/skill remove <name>`"
    user_id = _user_id(ctx)
    manager = get_plugin_manager()
    plugin = _find_user_plugin(manager, user_id, name)
    if not plugin:
        return f"❌ Plugin `{name}` is not installed for your account."

    manager.remove_user_plugin(user_id, plugin.name)
    if plugin.is_builtin:
        return f"🗑️ **Plugin `{plugin.name}` disabled for your account.**"

    from .user_state import any_user_has_skill

    if any_user_has_skill(plugin.name):
        return f"🗑️ **Plugin `{plugin.name}` removed from your account.**"

    result = uninstall(plugin.name)
    if result.get("ok"):
        manager.unregister(plugin.name)
        return f"🗑️ **Plugin `{plugin.name}` removed from your account and uninstalled from runtime.**"
    return f"⚠️ **Removed from your account, but runtime cleanup failed:** {result.get('message', 'unknown error')}"


async def handle_skill_enable(ctx, name: str, enable: bool = True) -> str:
    name = name.strip()
    if not name:
        return f"**Usage:** `/skill enable <name>`"
    user_id = _user_id(ctx)
    manager = get_plugin_manager()
    plugin = _find_user_plugin(manager, user_id, name)
    if not plugin:
        return f"❌ Plugin `{name}` is not installed for your account."
    manager.set_user_enabled(user_id, plugin.name, enable)
    status = "enabled" if enable else "disabled"
    return f"✅ **Plugin `{plugin.name}` {status} for your account.**"


async def handle_skill_info(ctx, name: str) -> str:
    name = name.strip()
    if not name:
        return f"**Usage:** `/skill info <name>`"
    user_id = _user_id(ctx)
    manager = get_plugin_manager()
    plugin = _find_user_plugin(manager, user_id, name)
    if not plugin:
        return f"❌ Plugin `{name}` is not installed for your account."
    status = "✅ enabled" if manager.is_enabled(plugin.name, user_id) else "❌ disabled"
    return "\n".join([
        f"🔌 **Plugin:** `{plugin.name}`",
        f"**Version:** {plugin.version}",
        f"**Status:** {status}",
        f"**Description:** {plugin.description or 'N/A'}",
        f"**Author:** {plugin.author or 'N/A'}",
        f"**Repository:** {plugin.repository or 'N/A'}",
        f"**Entry point:** `{plugin.entry_point or '(prompt-only skill)'}`",
        f"**Capabilities:** {', '.join(plugin.capabilities) or 'N/A'}",
        f"**Platforms:** {', '.join(plugin.platforms) or 'all'}",
        f"**Builtin:** {'Yes' if plugin.is_builtin else 'No'}",
        f"**Source:** `{plugin.source_path}`",
    ])


async def dispatch_skill_command(ctx, args: list[str]) -> str:
    if not args:
        return "**Usage:** `/skill <list|install|remove|enable|disable|info> [args]`"
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
    return f"❌ **Unknown subcommand:** `{sub}`. Use: `list`, `install`, `remove`, `enable`, `disable`, `info`."
