"""Plugin registry — manages plugin instances and their enabled/disabled state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BasePlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    def __init__(self):
        self._tools: list["BasePlugin"] = []
        self._enabled_names: set[str] = set()

    def register(self, plugin: "BasePlugin") -> None:
        self._tools.append(plugin)

    def unregister(self, name: str) -> bool:
        lowered = name.lower()
        before = len(self._tools)
        self._tools = [t for t in self._tools if t.name.lower() != lowered]
        self._enabled_names.discard(lowered)
        return len(self._tools) < before

    def disable(self, name: str) -> bool:
        lowered = name.lower()
        if lowered in self._enabled_names:
            self._enabled_names.discard(lowered)
            return True
        return False

    def enable(self, name: str) -> bool:
        lowered = name.lower()
        for plugin in self._tools:
            if plugin.name.lower() == lowered:
                self._enabled_names.add(lowered)
                return True
        return False

    def is_enabled(self, name: str) -> bool:
        return name.lower() in self._enabled_names

    def get_definitions(self, enabled_tools: str | list[str] | None = None) -> list[dict]:
        definitions: list[dict] = []
        for plugin in self._get_filtered(enabled_tools):
            definitions.extend(plugin.definitions())
        return definitions

    def process_tool_calls(
        self,
        user_id: int,
        tool_calls: list,
        enabled_tools: str | list[str] | None = None,
        event_callback=None,
    ) -> list[dict]:
        from .build import build_runnable
        from .events import emit_batch_event, set_event_callback, reset_event_callback

        token = set_event_callback(event_callback)
        try:
            filtered = self._get_filtered(enabled_tools)
            emit = lambda event_type, **payload: emit_batch_event(event_callback, user_id, event_type, **payload)
            emit_error = lambda idx, tool_name, **payload: emit("tool_error", index=idx, tool_name=tool_name, **payload)

            results, runnable, force_serial = build_runnable(tool_calls, filtered, emit_error)
            emit("tool_batch_start", count=len(runnable), total=len(tool_calls), serial=bool(force_serial))

            from .run import execute_runnable
            for idx, result in execute_runnable(user_id, runnable, force_serial=force_serial, emit=emit):
                results[idx] = result
            emit("tool_batch_end", count=len([item for item in results if item is not None]), total=len(tool_calls))
            return [item for item in results if item is not None]
        finally:
            reset_event_callback(token)

    def _get_filtered(self, enabled_tools: str | list[str] | None) -> list["BasePlugin"]:
        result: list["BasePlugin"] = []
        for plugin in self._tools:
            if not self.is_enabled(plugin.name):
                continue
            if enabled_tools is None or enabled_tools == "all":
                result.append(plugin)
            elif isinstance(enabled_tools, str):
                names = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]
                if "all" in names:
                    result.append(plugin)
                elif plugin.name.lower() in names:
                    result.append(plugin)
            elif isinstance(enabled_tools, list):
                if plugin.name.lower() in [t.lower() for t in enabled_tools]:
                    result.append(plugin)
        return result

    def get_instructions(self, enabled_tools: str | list[str] | None = None) -> str:
        return "".join(plugin.get_instruction() for plugin in self._get_filtered(enabled_tools))

    def enrich_system_prompt(self, user_id: int, prompt: str, enabled_tools: str | list[str] | None = None, **kwargs) -> str:
        for plugin in self._get_filtered(enabled_tools):
            prompt = plugin.enrich_system_prompt(user_id, prompt, **kwargs)
        return prompt

    def post_process(self, user_id: int, text: str, enabled_tools: str | list[str] | None = None) -> str:
        for plugin in self._get_filtered(enabled_tools):
            text = plugin.post_process(user_id, text)
        return text


# Global singleton
registry = PluginRegistry()
