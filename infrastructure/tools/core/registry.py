"""Tool registry: ToolEntry contract, @tool decorator, global registry."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Callable

from .schema import build_schema


@dataclass
class ToolEntry:
    name: str
    description: str
    toolset: str
    handler: Callable
    is_async: bool
    serial: bool = False
    risk: str = "safe"
    requires_env: tuple[str, ...] = ()
    check_fn: Callable[[], bool] | None = None
    max_result_chars: int = 20000
    dynamic_schema: Callable[[], dict] | None = None
    instruction: str = ""
    skill: str | None = None
    raw_args: bool = False
    _schema: dict | None = None

    def schema(self) -> dict:
        if self._schema is None:
            self._schema = build_schema(self.handler, name=self.name, description=self.description)
        if self.dynamic_schema is None:
            return self._schema
        override = self.dynamic_schema() or {}
        return {"type": "function", "function": {**self._schema["function"], **override}}


class ToolRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ToolEntry] = {}
        self._order: list[str] = []

    def register(self, entry: ToolEntry) -> None:
        if entry.name in self._entries:
            self._order.remove(entry.name)
        self._entries[entry.name] = entry
        self._order.append(entry.name)

    def unregister(self, name: str) -> bool:
        if name in self._entries:
            self._entries.pop(name)
            self._order.remove(name)
            return True
        return False

    def get(self, name: str) -> ToolEntry | None:
        return self._entries.get(name)

    def all(self) -> list[ToolEntry]:
        return [self._entries[name] for name in self._order]


registry = ToolRegistry()


def tool(
    *,
    toolset: str = "general",
    risk: str = "safe",
    serial: bool = False,
    requires_env: tuple[str, ...] = (),
    check_fn: Callable[[], bool] | None = None,
    max_result_chars: int = 20000,
    dynamic_schema: Callable[[], dict] | None = None,
    instruction: str = "",
    skill: str | None = None,
    name: str | None = None,
    description: str | None = None,
):
    def decorate(func):
        registry.register(ToolEntry(
            name=name or func.__name__,
            description=(description or inspect.getdoc(func) or func.__name__).strip(),
            toolset=toolset,
            handler=func,
            is_async=inspect.iscoroutinefunction(func),
            serial=serial,
            risk=risk,
            requires_env=tuple(requires_env),
            check_fn=check_fn,
            max_result_chars=max_result_chars,
            dynamic_schema=dynamic_schema,
            instruction=instruction,
            skill=skill,
        ))
        return func

    return decorate
