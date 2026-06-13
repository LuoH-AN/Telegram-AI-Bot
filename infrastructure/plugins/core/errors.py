"""Structured tool error payloads."""

from __future__ import annotations

import json
from typing import Any


def tool_error_content(
    *,
    tool_name: str | None,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "ok": False,
        "tool": tool_name or "",
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        payload["error"]["details"] = details
    return json.dumps(payload, ensure_ascii=False)
