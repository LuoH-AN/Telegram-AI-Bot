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
