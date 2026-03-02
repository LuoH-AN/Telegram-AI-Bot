"""Shared helpers for tool list normalization and fallback resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

AVAILABLE_TOOLS: tuple[str, ...] = (
    "memory",
    "search",
    "fetch",
    "wikipedia",
    "tts",
    "shell",
    "cron",
    "playwright",
    "crawl4ai",
    "browser_agent",
)

DEFAULT_ENABLED_TOOLS = "memory,search,fetch,wikipedia,tts"


def normalize_tools_csv(raw: str, *, allowed_tools: Sequence[str] = AVAILABLE_TOOLS) -> str:
    """Normalize comma-separated tool names while preserving canonical order."""
    allowed = set(allowed_tools)
    seen = set()
    ordered: list[str] = []
    for item in (raw or "").split(","):
        name = item.strip().lower()
        if not name or name not in allowed or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ",".join(ordered)


def resolve_enabled_tools_csv(settings: Mapping[str, object]) -> str:
    """Resolve enabled tools with default fallback for missing settings."""
    if "enabled_tools" not in settings:
        return normalize_tools_csv(DEFAULT_ENABLED_TOOLS)
    return normalize_tools_csv(str(settings.get("enabled_tools", "") or ""))


def resolve_cron_tools_csv(settings: Mapping[str, object]) -> str:
    """Resolve cron tool list with fallback to enabled tools excluding memory."""
    explicit = normalize_tools_csv(str(settings.get("cron_enabled_tools", "") or ""))
    if explicit:
        return explicit

    derived = normalize_tools_csv(str(settings.get("enabled_tools", "") or ""))
    derived_list = [name for name in derived.split(",") if name and name != "memory"]
    return ",".join(derived_list)
