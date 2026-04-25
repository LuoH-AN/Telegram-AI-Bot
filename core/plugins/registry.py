"""Plugin registry — wraps ToolRegistry and adds plugin-level state (enabled/disabled)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.core.base import BaseTool

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Manages plugins alongside their enabled/disabled state.

    Provides the same public API as the legacy ToolRegistry so that
    existing call sites (get_all_tools, process_tool_calls, etc.)
    continue to work unchanged.
    """

    def __init__(self):
        self._tools: list["BaseTool"] = []
        self._enabled_names: set[str] = set()

    def register(self, tool: "BaseTool") -> None:
        self._tools.append(tool)
        self._enabled_names.add(tool.name.lower())

    def disable(self, name: str) -> bool:
        lowered = name.lower()
        if lowered in self._enabled_names:
            self._enabled_names.discard(lowered)
            return True
        return False

    def enable(self, name: str) -> bool:
        lowered = name.lower()
        for tool in self._tools:
            if tool.name.lower() == lowered:
                self._enabled_names.add(lowered)
                return True
        return False

    def is_enabled(self, name: str) -> bool:
        return name.lower() in self._enabled_names

    def get_definitions(self, enabled_tools: str | list[str] | None = None) -> list[dict]:
        definitions: list[dict] = []
        for tool in self._get_filtered(enabled_tools):
            definitions.extend(tool.definitions())
        return definitions

    def process_tool_calls(
        self,
        user_id: int,
        tool_calls: list,
        enabled_tools: str | list[str] | None = None,
        event_callback=None,
    ) -> list[dict]:
        from tools.core.build import build_runnable
        from tools.core.events import emit_batch_event, set_event_callback, reset_event_callback

        token = set_event_callback(event_callback)
        try:
            filtered_tools = self._get_filtered(enabled_tools)
            emit = lambda event_type, **payload: emit_batch_event(event_callback, user_id, event_type, **payload)
            emit_error = lambda idx, tool_name, **payload: emit("tool_error", index=idx, tool_name=tool_name, **payload)

            results, runnable, force_serial = build_runnable(tool_calls, filtered_tools, emit_error)
            emit("tool_batch_start", count=len(runnable), total=len(tool_calls), serial=bool(force_serial))

            from tools.core.run import execute_runnable
            for idx, result in execute_runnable(user_id, runnable, force_serial=force_serial, emit=emit):
                results[idx] = result
            emit("tool_batch_end", count=len([item for item in results if item is not None]), total=len(tool_calls))
            return [item for item in results if item is not None]
        finally:
            reset_event_callback(token)

    def _get_filtered(self, enabled_tools: str | list[str] | None) -> list["BaseTool"]:
        result: list["BaseTool"] = []
        for tool in self._tools:
            if not self.is_enabled(tool.name):
                continue
            if enabled_tools is None or enabled_tools == "all":
                result.append(tool)
            elif isinstance(enabled_tools, str):
                names = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]
                if "all" in names:
                    result.append(tool)
                elif tool.name.lower() in names:
                    result.append(tool)
            elif isinstance(enabled_tools, list):
                if tool.name.lower() in [t.lower() for t in enabled_tools]:
                    result.append(tool)
        return result

    def get_instructions(self, enabled_tools: str | list[str] | None = None) -> str:
        return "".join(tool.get_instruction() for tool in self._get_filtered(enabled_tools))

    def enrich_system_prompt(self, user_id: int, prompt: str, enabled_tools: str | list[str] | None = None, **kwargs) -> str:
        for tool in self._get_filtered(enabled_tools):
            prompt = tool.enrich_system_prompt(user_id, prompt, **kwargs)
        return prompt

    def post_process(self, user_id: int, text: str, enabled_tools: str | list[str] | None = None) -> str:
        for tool in self._get_filtered(enabled_tools):
            text = tool.post_process(user_id, text)
        return text


# Global singleton — aliased as "registry" for compatibility with tools/__init__.py
registry = PluginRegistry()
