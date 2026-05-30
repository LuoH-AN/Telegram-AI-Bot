"""Human-friendly tool status text helpers."""

from __future__ import annotations

from typing import Any


def build_tool_status_text(event: dict[str, Any]) -> str | None:
    """One consolidated message: each requested tool call on its own line, no args."""
    if str(event.get("type") or "").strip() != "tool_batch_start":
        return None
    names = event.get("tool_names") or []
    lines = [f"🔧 {str(name or '').strip() or 'tool'}" for name in names]
    return "\n".join(lines) if lines else None
