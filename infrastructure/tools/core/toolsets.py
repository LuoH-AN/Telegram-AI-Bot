"""Toolset grouping, composition (includes), and scenario allowlists."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Toolset:
    name: str
    description: str = ""
    tools: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)


_REGISTRY: dict[str, Toolset] = {}


def define_toolset(name: str, *, description: str = "", tools=(), includes=()) -> Toolset:
    ts = Toolset(name=name, description=description, tools=list(tools), includes=list(includes))
    _REGISTRY[name] = ts
    return ts


def get_toolset(name: str) -> Toolset | None:
    return _REGISTRY.get(name)


def resolve(toolset_names: list[str]) -> set[str]:
    out: set[str] = set()
    seen: set[str] = set()

    def walk(name: str) -> None:
        ts = _REGISTRY.get(name)
        if ts is None or name in seen:
            return
        seen.add(name)
        out.update(ts.tools)
        for inc in ts.includes:
            walk(inc)

    for name in toolset_names:
        walk(name)
    return out


# Scenario allowlist for untrusted input sources (group chats, webhooks).
UNTRUSTED_SAFE_TOOLS = {"search", "terminal_bg_list", "terminal_bg_check"}
