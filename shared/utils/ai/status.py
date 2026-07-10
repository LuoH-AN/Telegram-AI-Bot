"""Human-friendly tool status text helpers."""

from __future__ import annotations


def build_tool_status_text(tool_names: list[str]) -> str | None:
    """One line per distinct tool call, with a ×N count when repeated."""
    counts: dict[str, int] = {}
    for name in tool_names or []:
        clean = str(name or "").strip() or "tool"
        counts[clean] = counts.get(clean, 0) + 1
    lines = [f"🔧 {name}" + (f" ×{count}" if count > 1 else "") for name, count in counts.items()]
    return "\n".join(lines) if lines else None


def build_tool_progress_text(
    states: dict[str, str],
    *,
    lang: str = "en",
    mode: str = "full",
) -> str | None:
    if mode == "off":
        return None
    labels = {
        "search": ("搜索资料", "Searching"),
        "save_memory": ("保存记忆", "Saving memory"),
        "list_memories": ("读取记忆", "Reading memories"),
        "send_file": ("准备文件", "Preparing file"),
        "terminal": ("执行命令", "Running command"),
        "user_cron": ("更新定时任务", "Updating schedule"),
        "config_file": ("更新配置", "Updating configuration"),
    }
    zh = (lang or "").startswith("zh")
    if mode == "compact":
        active = [(name, state) for name, state in states.items() if state != "done"][-3:]
        lines = []
        for name, state in active:
            label = labels.get(name, (name, name))[0 if zh else 1]
            if state == "error":
                lines.append(f"⚠️ {label}" + ("失败" if zh else " failed"))
            else:
                lines.append(f"⏳ {label}…")
        completed = sum(1 for state in states.values() if state == "done")
        if completed:
            lines.append(f"✅ 已完成 {completed} 项" if zh else f"✅ {completed} completed")
        return "\n".join(lines) if lines else None
    lines: list[str] = []
    for name, state in list(states.items())[-8:]:
        label = labels.get(name, (name, name))[0 if zh else 1]
        if state == "done":
            lines.append(f"✅ {label}" + ("完成" if zh else " complete"))
        elif state == "error":
            lines.append(f"⚠️ {label}" + ("失败" if zh else " failed"))
        else:
            lines.append(f"⏳ {label}…")
    return "\n".join(lines) if lines else None
