"""Tool registry — BaseTool base class, registration, and dispatch."""

import json
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

TOOL_CALL_MAX_WORKERS = 4
# Tools with side effects/order sensitivity run serially within a batch.
SERIAL_ONLY_TOOL_NAMES = {
    "save_memory",
    "cron_create",
    "cron_delete",
    "cron_run",
    "shell_exec",
}


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
            List of tool result messages (always returned so the AI can
            generate a follow-up response even after fire-and-forget tools).
        """
        # Build name -> tool lookup from enabled tools
        name_map: dict[str, BaseTool] = {}
        for tool in self._get_filtered_tools(enabled_tools):
            for defn in tool.definitions():
                name_map[defn["function"]["name"]] = tool

        # Keep output order stable to match input tool_calls order.
        results: list[dict | None] = [None] * len(tool_calls)
        runnable: list[tuple[int, object, BaseTool, str, dict]] = []
        force_serial = False

        for idx, tc in enumerate(tool_calls):
            tc_name = tc.name.strip() if tc.name else tc.name
            if tc_name in SERIAL_ONLY_TOOL_NAMES:
                force_serial = True
            tool = name_map.get(tc_name)
            if tool is None:
                logger.warning(f"No enabled tool registered for '{tc_name}'")
                results[idx] = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Error: Unknown tool '{tc_name}'",
                }
                continue
            try:
                args = json.loads(tc.arguments)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool call arguments: {e}")
                results[idx] = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Error: Invalid arguments - {e}",
                }
                continue
            runnable.append((idx, tc, tool, tc_name, args))

        def _execute_one(item: tuple[int, object, BaseTool, str, dict]) -> tuple[int, dict]:
            idx, tc, tool, tc_name, args = item
            try:
                result = tool.execute(user_id, tc_name, args)
            except Exception as e:
                logger.exception("[user=%d] tool execution failed: %s", user_id, tc_name)
                return idx, {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Error: Tool execution failed - {e}",
                }
            logger.info("[user=%d] tool call: %s(%s)", user_id, tc_name, json.dumps(args, ensure_ascii=False)[:200])
            if result is not None:
                logger.info("[user=%d] tool result: %s (%d chars)", user_id, tc_name, len(result))
            else:
                logger.info("[user=%d] tool result: %s -> OK (fire-and-forget)", user_id, tc_name)
            return idx, {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result if result is not None else "OK",
            }

        if len(runnable) == 1 or force_serial:
            if force_serial and len(runnable) > 1:
                logger.info(
                    "[user=%d] serial-only tool detected, executing %d tool calls serially",
                    user_id,
                    len(runnable),
                )
            for item in runnable:
                idx, result = _execute_one(item)
                results[idx] = result
        elif runnable:
            workers = min(TOOL_CALL_MAX_WORKERS, len(runnable))
            logger.info(
                "[user=%d] executing %d tool calls in parallel (workers=%d)",
                user_id,
                len(runnable),
                workers,
            )
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tool-call") as pool:
                futures = [pool.submit(_execute_one, item) for item in runnable]
                for future in futures:
                    idx, result = future.result()
                    results[idx] = result

        return [result for result in results if result is not None]

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
