"""Aggregate project status text for the /status command."""

from __future__ import annotations

import os
import sys
import time

try:
    import resource as _resource
except ImportError:
    _resource = None

from infrastructure.cache import cache
from infrastructure.runtime import PROCESS_START_TIME

from .token import get_total_tokens_all_personas
from .update import git_info


def _format_uptime(seconds: float) -> str:
    total = int(max(0, seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _memory_mb() -> str:
    if _resource is None:
        return "n/a"
    rss_kb = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    return f"{max(1, rss_kb) // 1024} MB"


def _plugin_names() -> list[str]:
    try:
        from infrastructure.tools.skills.manager import get_skill_manager
        return [manifest.name for manifest in get_skill_manager().list_manifests()]
    except Exception:
        return []


def build_status_text(user_id: int) -> str:
    git = git_info()
    stats = cache.runtime_stats()
    lines = ["🟢 **Project Status**", ""]

    if git.get("available"):
        workdir = "clean" if git["changed_files"] == 0 else f"{git['changed_files']} uncommitted"
        lines += [
            "📦 **Code**",
            f"• Branch: `{git['branch']}`",
            f"• Commit: `{git['commit']}`",
            f"• Workdir: {workdir}",
            "",
        ]

    python = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    mode = "managed" if os.getenv("BOT_LAUNCHER_MANAGED") == "1" else "standalone"
    lines += [
        "⚙️ **Runtime**",
        f"• Uptime: {_format_uptime(time.time() - PROCESS_START_TIME)}",
        f"• Memory: {_memory_mb()}",
        f"• Python: {python}",
        f"• Mode: {mode}",
        "",
        "💾 **Data**",
        f"• Users: {stats['users']}",
        f"• Sessions: {stats['sessions']}",
        f"• Messages: {stats['messages']:,}",
        f"• Cron tasks: {stats['cron_tasks']}",
        "",
    ]

    plugins = _plugin_names()
    if plugins:
        lines += [f"🧩 **Plugins** ({len(plugins)})", ", ".join(f"`{name}`" for name in plugins), ""]

    lines.append(f"📊 **Your tokens**: {get_total_tokens_all_personas(user_id):,}")
    return "\n".join(lines)
