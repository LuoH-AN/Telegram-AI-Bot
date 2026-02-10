"""Tool registry — BaseTool base class, registration, and dispatch."""

import json
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Abstract base class for tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier for this tool (e.g. 'search', 'memory')."""

    @abstractmethod
    def definitions(self) -> list[dict]:
        """Return OpenAI function-calling format tool definitions."""

    @abstractmethod
    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        """Execute a tool call, return result text (or None)."""

    def get_instruction(self) -> str:
        """Extra instruction appended to system prompt. Default empty."""
        return ""

    def enrich_system_prompt(self, user_id: int, system_prompt: str, **kwargs) -> str:
        """Inject context into system prompt. Default no-op."""
        return system_prompt

    def post_process(self, user_id: int, text: str) -> str:
        """Post-process AI response text. Default no-op."""
        return text


class ToolRegistry:
    def __init__(self):
        self._tools: list[BaseTool] = []

    def register(self, tool: BaseTool):
        self._tools.append(tool)

    def _get_filtered_tools(self, enabled_tools: str | list[str] | None) -> list[BaseTool]:
        """Filter registered tools by enabled names."""
        if enabled_tools is None:
            return self._tools
        
        if isinstance(enabled_tools, str):
            enabled_list = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]
        else:
            enabled_list = [t.lower() for t in enabled_tools]
            
        return [t for t in self._tools if t.name.lower() in enabled_list]

    # -- public API --

    def get_definitions(self, enabled_tools: str | list[str] | None = None) -> list[dict]:
        """Merge filtered tool definitions."""
        defs = []
        for tool in self._get_filtered_tools(enabled_tools):
            defs.extend(tool.definitions())
        return defs

    def process_tool_calls(self, user_id: int, tool_calls: list, enabled_tools: str | list[str] | None = None) -> list[dict]:
        """Dispatch tool calls to the matching tool's execute().

        Returns:
            List of tool result messages if any tool returned a result,
            empty list if all tools are fire-and-forget (returned None).
        """
        # Build name -> tool lookup from enabled tools
        name_map: dict[str, BaseTool] = {}
        for tool in self._get_filtered_tools(enabled_tools):
            for defn in tool.definitions():
                name_map[defn["function"]["name"]] = tool

        results = []
        has_results = False
        for tc in tool_calls:
            tool = name_map.get(tc.name)
            if tool is None:
                logger.warning(f"No enabled tool registered for '{tc.name}'")
                continue
            try:
                args = json.loads(tc.arguments)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool call arguments: {e}")
                continue
            result = tool.execute(user_id, tc.name, args)
            if result is not None:
                has_results = True
            results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result if result is not None else "OK",
            })
        return results if has_results else []

    def get_instructions(self, enabled_tools: str | list[str] | None = None) -> str:
        """Concatenate filtered tools' instruction strings."""
        parts = [t.get_instruction() for t in self._get_filtered_tools(enabled_tools)]
        return "".join(parts)

    def enrich_system_prompt(self, user_id: int, prompt: str, enabled_tools: str | list[str] | None = None, **kwargs) -> str:
        """Let every enabled tool enrich the system prompt in order."""
        for tool in self._get_filtered_tools(enabled_tools):
            prompt = tool.enrich_system_prompt(user_id, prompt, **kwargs)
        return prompt

    def post_process(self, user_id: int, text: str, enabled_tools: str | list[str] | None = None) -> str:
        """Let every enabled tool post-process the AI response in order."""
        for tool in self._get_filtered_tools(enabled_tools):
            text = tool.post_process(user_id, text)
        return text


# Singleton
registry = ToolRegistry()
