"""Aggregate project status text for the /status command."""

from __future__ import annotations

import logging
import os
import sys
import time

from shared.utils.format import format_count

try:
    import resource as _resource
except ImportError:
    _resource = None

from infrastructure.cache import cache
from infrastructure.runtime import PROCESS_START_TIME

from .token import get_total_tokens_all_personas
from .update import git_info

logger = logging.getLogger(__name__)


def _format_uptime(seconds: float, lang: str = "en") -> str:
    total = int(max(0, seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if lang == "zh":
        if days:
            return f"{days} 天 {hours} 小时 {minutes} 分钟"
        if hours:
            return f"{hours} 小时 {minutes} 分钟"
        return f"{minutes} 分钟"
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _memory_mb() -> int | None:
    if _resource is None:
        return None
    rss_kb = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    return max(1, rss_kb) // 1024


def _cgroup_limit_mb() -> int | None:
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path) as f:
                value = int(f.read().strip())
        except (OSError, ValueError):
            continue
        if 0 < value < 1 << 44:  # sane container limit (< 16 TB)
            return value // (1024 * 1024)
    return None


def _memory_bar() -> str:
    mb = _memory_mb()
    if mb is None:
        return "n/a"
    limit = _cgroup_limit_mb()
    if not limit:
        return f"{mb:,} MB"
    percent = min(100.0, mb / limit * 100)
    status = "🔴" if percent >= 90 else ("🟡" if percent >= 70 else "🟢")
    return f"{status} {mb:,} / {limit:,} MB ({percent:.0f}%)"


def _plugin_names() -> list[str]:
    try:
        from infrastructure.tools.skills.manager import get_skill_manager
        return [manifest.name for manifest in get_skill_manager().list_manifests()]
    except Exception:
        logger.warning("skill manager unavailable; status will omit skill list", exc_info=True)
        return []


def build_status_text(user_id: int, *, lang: str = "en") -> str:
    git = git_info()
    stats = cache.runtime_stats()
    lines = ["🟢 **项目运行状态**" if lang == "zh" else "🟢 **Project Status**", ""]

    if git.get("available"):
        if lang == "zh":
            workdir = "干净" if git["changed_files"] == 0 else f"{git['changed_files']} 个未提交文件"
        else:
            workdir = "clean" if git["changed_files"] == 0 else f"{git['changed_files']} uncommitted"
        lines += [
            "📦 **代码**" if lang == "zh" else "📦 **Code**",
            f"• {'分支' if lang == 'zh' else 'Branch'}: `{git['branch']}`",
            f"• {'提交' if lang == 'zh' else 'Commit'}: `{git['commit']}`",
            f"• {'工作区' if lang == 'zh' else 'Workdir'}: {workdir}",
            "",
        ]

    python = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if lang == "zh":
        mode = "🛡️ 启动器托管" if os.getenv("BOT_LAUNCHER_MANAGED") == "1" else "🖥️ 独立运行"
    else:
        mode = "🛡️ managed" if os.getenv("BOT_LAUNCHER_MANAGED") == "1" else "🖥️ standalone"
    lines += [
        "⚙️ **运行环境**" if lang == "zh" else "⚙️ **Runtime**",
        f"• {'运行时间' if lang == 'zh' else 'Uptime'}: ⏱️ {_format_uptime(time.time() - PROCESS_START_TIME, lang)}",
        f"• {'内存' if lang == 'zh' else 'Memory'}: {_memory_bar()}",
        f"• Python: {python}",
        f"• {'模式' if lang == 'zh' else 'Mode'}: {mode}",
        "",
        "💾 **数据**" if lang == "zh" else "💾 **Data**",
        f"• 👤 {'用户' if lang == 'zh' else 'Users'}: {stats['users']}",
        f"• 💬 {'会话' if lang == 'zh' else 'Sessions'}: {stats['sessions']}",
        f"• ✉️ {'消息' if lang == 'zh' else 'Messages'}: {format_count(stats['messages'])}",
        f"• ⏰ {'定时任务' if lang == 'zh' else 'Cron tasks'}: {stats['cron_tasks']}",
        "",
    ]

    plugins = _plugin_names()
    if plugins:
        lines += [f"🧩 **{'插件' if lang == 'zh' else 'Plugins'}** ({len(plugins)})", ", ".join(f"`{name}`" for name in plugins), ""]

    from shared.utils.format import format_tokens

    lines.append(f"📊 **{'你的 Token 用量' if lang == 'zh' else 'Your tokens'}**: {format_tokens(get_total_tokens_all_personas(user_id))}")
    return "\n".join(lines)
