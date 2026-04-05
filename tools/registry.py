"""Tool registry — registration, filtering and dispatch."""

from __future__ import annotations

from .base import BaseTool
from .registry_build import build_runnable
from .registry_events import (
    ToolEventCallback,
    emit_batch_event,
    emit_tool_progress,
    reset_event_callback,
    set_event_callback,
)
from .registry_run import execute_runnable


class ToolRegistry:
    def __init__(self):
        self._tools: list[BaseTool] = []

    def register(self, tool: BaseTool):
        self._tools.append(tool)

    def _get_filtered_tools(self, enabled_tools: str | list[str] | None) -> list[BaseTool]:
        if enabled_tools is None or enabled_tools == "all":
            return self._tools
        names = [t.strip().lower() for t in enabled_tools.split(",")] if isinstance(enabled_tools, str) else [t.lower() for t in enabled_tools]
        names = [name for name in names if name]
        if "all" in names:
            return self._tools
        return [tool for tool in self._tools if tool.name.lower() in names]

    def get_definitions(self, enabled_tools: str | list[str] | None = None) -> list[dict]:
        definitions: list[dict] = []
        for tool in self._get_filtered_tools(enabled_tools):
            definitions.extend(tool.definitions())
        return definitions

    def process_tool_calls(
        self,
        user_id: int,
        tool_calls: list,
        enabled_tools: str | list[str] | None = None,
        event_callback: ToolEventCallback | None = None,
    ) -> list[dict]:
        token = set_event_callback(event_callback)
        try:
            filtered_tools = self._get_filtered_tools(enabled_tools)
            emit = lambda event_type, **payload: emit_batch_event(event_callback, user_id, event_type, **payload)
            emit_error = lambda idx, tool_name, **payload: emit("tool_error", index=idx, tool_name=tool_name, **payload)
            results, runnable, force_serial = build_runnable(tool_calls, filtered_tools, emit_error)
            emit("tool_batch_start", count=len(runnable), total=len(tool_calls), serial=bool(force_serial))

            for idx, result in execute_runnable(user_id, runnable, force_serial=force_serial, emit=emit):
                results[idx] = result
            emit("tool_batch_end", count=len([item for item in results if item is not None]), total=len(tool_calls))
            return [item for item in results if item is not None]
        finally:
            reset_event_callback(token)

    def get_instructions(self, enabled_tools: str | list[str] | None = None) -> str:
        return "".join(tool.get_instruction() for tool in self._get_filtered_tools(enabled_tools))

    def enrich_system_prompt(self, user_id: int, prompt: str, enabled_tools: str | list[str] | None = None, **kwargs) -> str:
        for tool in self._get_filtered_tools(enabled_tools):
            prompt = tool.enrich_system_prompt(user_id, prompt, **kwargs)
        return prompt

    def post_process(self, user_id: int, text: str, enabled_tools: str | list[str] | None = None) -> str:
        for tool in self._get_filtered_tools(enabled_tools):
            text = tool.post_process(user_id, text)
        return text


registry = ToolRegistry()

