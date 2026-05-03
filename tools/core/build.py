"""Build runnable tool call batches from model tool_calls."""

from __future__ import annotations

import json
import logging

from .base import BaseTool

logger = logging.getLogger(__name__)

SERIAL_ONLY_TOOL_NAMES = {
    "save_memory", "cron_create", "cron_delete", "cron_run", "shell_exec", "project_config",
}


def _parse_arguments(tool_call) -> dict:
    raw = tool_call.arguments if isinstance(tool_call.arguments, str) else str(tool_call.arguments or "")
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```")).strip()
    if not text or text.lower() == "null":
        return {}
    args = json.loads(text)
    if not isinstance(args, dict):
        raise ValueError("arguments must be a JSON object")
    return args


def build_runnable(
    tool_calls: list,
    tools: list[BaseTool],
    emit_error,
) -> tuple[list[dict | None], list[tuple[int, object, BaseTool, str, dict]], bool]:
    name_map: dict[str, BaseTool] = {}
    for tool in tools:
        for definition in tool.definitions():
            name_map[definition["function"]["name"]] = tool

    results: list[dict | None] = [None] * len(tool_calls)
    runnable: list[tuple[int, object, BaseTool, str, dict]] = []
    force_serial = False

    for idx, tool_call in enumerate(tool_calls):
        tool_name = tool_call.name.strip() if tool_call.name else tool_call.name
        if tool_name in SERIAL_ONLY_TOOL_NAMES:
            force_serial = True

        tool = name_map.get(tool_name)
        if tool is None:
            logger.warning("No enabled tool registered for '%s'", tool_name)
            emit_error(idx, tool_name, reason="unknown_tool")
            results[idx] = {"role": "tool", "tool_call_id": tool_call.id, "content": f"Error: Unknown tool '{tool_name}'"}
            continue

        try:
            args = _parse_arguments(tool_call)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse tool call arguments for %s: %s", tool_name, exc)
            emit_error(idx, tool_name, reason="invalid_arguments", message=str(exc))
            results[idx] = {"role": "tool", "tool_call_id": tool_call.id, "content": f"Error: Invalid arguments - {exc}"}
            continue

        runnable.append((idx, tool_call, tool, tool_name, args))

    return results, runnable, force_serial
