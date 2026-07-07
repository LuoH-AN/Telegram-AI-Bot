"""Framework-level structured tool error payloads."""

from __future__ import annotations

import json
from typing import Any


def error_content(code: str, message: str, **details: Any) -> str:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return json.dumps(payload, ensure_ascii=False)
