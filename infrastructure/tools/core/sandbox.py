"""Terminal command policy: block destructive ops, escalate risky ones."""

from __future__ import annotations

import os
import re

DENY = (
    re.compile(r"\brm\s+-rf?\s+/(?:\s|$|[*])"),
    re.compile(r"\bmkfs\b"),
    re.compile(r":\(\)\s*\{.*:.*&.*\}.*;"),
    re.compile(r"\bdd\b.*\bof=/dev/"),
    re.compile(r">\s*/dev/sd[a-z]"),
    re.compile(r"\b(?:shutdown|reboot|halt|poweroff)\b"),
)

RISKY = (
    re.compile(r"\brm\s+-r"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bchmod\s+[0-7]*777\b"),
    re.compile(r"\bgit\s+push\b.*--force"),
    re.compile(r"\b(?:curl|wget)\b.*\|\s*(?:ba)?sh"),
    re.compile(r"\b>\s*/etc/"),
)


def _confirm_enabled() -> bool:
    return os.getenv("TERMINAL_CONFIRM", "1").strip().lower() in ("1", "true", "yes", "on")


def classify(command: str) -> str:
    text = command or ""
    if any(pattern.search(text) for pattern in DENY):
        return "block"
    if _confirm_enabled() and any(pattern.search(text) for pattern in RISKY):
        return "escalate"
    return "allow"
