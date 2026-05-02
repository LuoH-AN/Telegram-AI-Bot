"""Tool-call helpers for streaming generation."""

from __future__ import annotations


def build_assistant_tool_call_message(full_response: str, tool_calls: list) -> dict:
    return {
        "role": "assistant",
        "content": full_response or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in tool_calls
        ],
    }
