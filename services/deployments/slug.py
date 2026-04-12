"""Slug helpers for public deployments."""

from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def normalize_slug(value: str, *, fallback: str = "site") -> str:
    text = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    text = _SLUG_RE.sub("-", text).strip("-")
    return text or fallback
