"""Tool execution context and unified result type."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class ToolContext:
    """Injected into every tool call — replaces globals and adapter imports."""
    user_id: int
    chat_id: int | None = None
    outbound: Any = None
    env: dict[str, str] = field(default_factory=dict)
    confirm: Callable[..., Awaitable[str]] | None = None
    emit: Callable[[str], None] | None = None


@dataclass
class ToolResult:
    """Single return type for all tools. `.content` is the model-facing string."""
    content: str
    ok: bool = True
    kind: str = "text"

    @classmethod
    def text(cls, content: str) -> "ToolResult":
        return cls(content=str(content), ok=True, kind="text")

    @classmethod
    def data(cls, payload: Any) -> "ToolResult":
        return cls(content=json.dumps(payload, ensure_ascii=False), ok=True, kind="data")

    @classmethod
    def error(cls, code: str, message: str, **details: Any) -> "ToolResult":
        error: dict[str, Any] = {"code": code, "message": message}
        if details:
            error["details"] = details
        return cls(
            content=json.dumps({"ok": False, "error": error}, ensure_ascii=False),
            ok=False,
            kind="error",
        )
