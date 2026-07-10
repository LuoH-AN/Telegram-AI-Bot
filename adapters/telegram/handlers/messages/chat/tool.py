"""Tool-call helpers for streaming generation."""

from __future__ import annotations

import json


def build_assistant_tool_call_message(full_response: str, tool_calls: list, reasoning_content: str | None = None) -> dict:
    msg: dict = {
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
    if reasoning_content:
        msg["reasoning_content"] = reasoning_content
    return msg


def build_tool_limit_results(tool_calls: list, limit: int) -> list[dict]:
    content = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "tool_round_limit",
                "message": f"Tool-call limit reached ({limit} rounds). Use the evidence already collected and answer now.",
            },
        },
        ensure_ascii=False,
    )
    return [{"role": "tool", "tool_call_id": tool_call.id, "content": content} for tool_call in tool_calls]
