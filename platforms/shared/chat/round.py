"""Single response generation round with tool-calls."""

from __future__ import annotations

import asyncio
from typing import Callable

from ai import get_ai_client
from config import SHOW_THINKING_MAX_CHARS
from ai.stream import stream_response
from utils.ai import extract_thinking_blocks, filter_thinking_content, format_thinking_block


async def run_completion_round(
    *,
    user_id: int,
    settings: dict,
    messages: list[dict],
    user_reasoning_effort: str,
    show_thinking: bool,
    tool_event_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Run a single completion round with tool call support.

    Args:
        user_id: User ID for AI client.
        settings: User settings containing model and temperature.
        messages: Conversation messages.
        user_reasoning_effort: Reasoning effort level.
        show_thinking: Whether to show thinking blocks.
        tool_event_callback: Optional callback for tool events.

    Returns:
        Dict with final_text, display_final, messages, and token usage.
    """
    from plugins import get_all_tools, process_tool_calls

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_thinking_seconds = 0.0
    truncated_prefix = ""
    last_text_response = ""
    thinking_segments: list[str] = []
    tool_definitions = get_all_tools(enabled_tools="all")

    async def _noop(_text: str) -> bool:
        return True

    while True:
        full, usage, thinking_sec, finish_reason, reasoning_content, tool_calls = await stream_response(
            get_ai_client(user_id),
            messages,
            settings["model"],
            settings["temperature"],
            user_reasoning_effort,
            _noop,
            _noop,
            show_waiting=False,
            stream_mode="off",
            include_thought_prefix=False,
            stream_cursor=False,
            show_thinking=show_thinking,
            thinking_max_chars=SHOW_THINKING_MAX_CHARS,
            tools=tool_definitions,
        )
        total_thinking_seconds += thinking_sec
        if show_thinking:
            tag_thinking, _ = extract_thinking_blocks(full)
            for segment in (reasoning_content, tag_thinking):
                cleaned = (segment or "").strip()
                if cleaned and (not thinking_segments or thinking_segments[-1] != cleaned):
                    thinking_segments.append(cleaned)
        if usage:
            total_prompt_tokens += usage.get("prompt_tokens") or 0
            total_completion_tokens += usage.get("completion_tokens") or 0
        if full.strip():
            last_text_response = full
        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": full or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments}
                    }
                    for tc in tool_calls
                ],
            })
            tool_results = await asyncio.to_thread(process_tool_calls, user_id, tool_calls, "all", tool_event_callback)
            messages.extend(tool_results)
            continue
        if finish_reason == "length":
            truncated = full or ""
            truncated_prefix += truncated
            messages.append({"role": "assistant", "content": truncated})
            messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
            continue
        break

    combined = truncated_prefix + last_text_response if truncated_prefix else last_text_response
    final_text = filter_thinking_content(combined).strip() or filter_thinking_content(last_text_response).strip() or "(Empty response)"
    thinking_block = ""
    if show_thinking and thinking_segments:
        thinking_block = format_thinking_block("\n\n".join(thinking_segments).strip(), seconds=total_thinking_seconds, max_chars=SHOW_THINKING_MAX_CHARS)
    return {
        "messages": messages,
        "final_text": final_text,
        "display_final": thinking_block + final_text if thinking_block else final_text,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
    }
