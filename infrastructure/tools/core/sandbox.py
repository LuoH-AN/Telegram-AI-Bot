"""Terminal command policy: block destructive ops, escalate risky ones."""

from __future__ import annotations

import os
import re

# Recursive rm (rm with an -r flag) targeting a system/user root or wildcard.
_RM_ROOT_TARGETS = (
    r"/(?:[\s*]|$)",            # /, /*, /<end>
    r"/(?:home|etc|usr|var|lib|lib64|boot|root|opt|srv|bin|sbin|proc|sys|dev)(?:[\s/]|$)",
    r"~(?:[\s/]|$)",            # ~, ~/...
    r"\$HOME\b",
    r"\*(?:\s|$)",              # bare wildcard
)

DENY = (
    re.compile(r"\brm\b[^|;&\n]*-[A-Za-z]*r[A-Za-z]*(?:[^|;&\n]*\s+)(" + "|".join(_RM_ROOT_TARGETS) + r")", re.I),
    re.compile(r":\s*\(\s*\)\s*\{"),                                   # fork bomb
    re.compile(r"\bmkfs\w*\b", re.I),
    re.compile(r"\bdd\b[^|;&\n]*\bof\s*=\s*/dev/", re.I),              # dd to block device
    re.compile(r">\s*/dev/(?:sd|nvme|vd|xvd|hd|disk)", re.I),          # write to disk device
    re.compile(r"\b(?:shutdown|reboot|halt|poweroff|init\s+0)\b", re.I),
    re.compile(r"\bfind\b[^|;&\n]*\s+/(?:[\s])[^|;&\n]*-delete", re.I),  # find / ... -delete
    re.compile(r"\bchmod\b[^|;&\n]*-R[^|;&\n]*\s+(?:/(?:[\s*]|$)|/(?:etc|usr|bin|sbin|lib|boot)(?:[\s/]|$)|~)", re.I),
    re.compile(r"\b(?:mv|cp)\b[^|;&\n]*\s+(?:/(?:dev|proc|sys|boot)(?:[\s/]|$))", re.I),
)

RISKY = (
    re.compile(r"\brm\b[^|;&\n]*-[A-Za-z]*r", re.I),     # any recursive remove
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\bchmod\b[^|;&\n]*\b777\b", re.I),
    re.compile(r"\bgit\b[^|;&\n]*push[^|;&\n]*--(?:force|f)\b", re.I),
    re.compile(r"\b(?:curl|wget)\b", re.I),              # network egress (covers |sh too)
    re.compile(r">\s*/etc/", re.I),
    re.compile(r"\b(?:bash|sh|zsh|fish|python\d?|perl|ruby|node)\b[^|;&\n]*<\s*(?:/dev/|https?://|ftp://)", re.I),
    re.compile(r"\b(?:mv|chmod|chown)\b[^|;&\n]*-R\b", re.I),
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
