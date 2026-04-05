"""Streaming response generation with tool-calls."""

from __future__ import annotations

import asyncio
import logging

from config import SHOW_THINKING_MAX_CHARS, STREAM_UPDATE_MODE
from utils import filter_thinking_content

from ..streaming import stream_response
from .generation_tools import build_assistant_tool_call_message
from .helpers import append_thinking_segments, build_final_display, normalize_reasoning_effort

logger = logging.getLogger(__name__)


async def generate_with_tools(
    *,
    client,
    messages: list[dict],
    settings: dict,
    user_id: int,
    ctx: str,
    runtime,
) -> dict:
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_thinking_seconds = 0.0
    truncated_prefix = ""
    last_text_response = ""
    thinking_segments: list[str] = []
    full_response = ""
    user_stream_mode = settings.get("stream_mode", "") or STREAM_UPDATE_MODE
    user_reasoning_effort = normalize_reasoning_effort(settings.get("reasoning_effort", ""))
    show_thinking = bool(settings.get("show_thinking"))
    from tools import get_all_tools, process_tool_calls
    tool_definitions = get_all_tools(enabled_tools="all")

    while True:
        full_response, usage_info, thinking_seconds, finish_reason, reasoning_content, tool_calls = await stream_response(
            client, messages, settings["model"], settings["temperature"], user_reasoning_effort,
            runtime.stream_update, runtime.status_update, show_waiting=(not truncated_prefix),
            stream_mode=user_stream_mode, include_thought_prefix=True, stream_cursor=True,
            show_thinking=show_thinking, thinking_max_chars=SHOW_THINKING_MAX_CHARS, tools=tool_definitions,
        )
        total_thinking_seconds += thinking_seconds
        append_thinking_segments(show_thinking=show_thinking, full_response=full_response, reasoning_content=reasoning_content, segments=thinking_segments)
        if usage_info:
            total_prompt_tokens += usage_info.get("prompt_tokens") or 0
            total_completion_tokens += usage_info.get("completion_tokens") or 0
        if full_response.strip():
            last_text_response = full_response
        if tool_calls:
            logger.info("%s model requested %d tool calls", ctx, len(tool_calls))
            if full_response.strip():
                await runtime.render_pump.drain()
                visible = filter_thinking_content(full_response).strip()
                if visible:
                    await runtime.outbound.deliver_final(visible)
                    runtime.clear_placeholder()
            tool_results = await asyncio.to_thread(
                process_tool_calls,
                user_id,
                tool_calls,
                "all",
                runtime.tool_event_callback,
            )
            messages.append(build_assistant_tool_call_message(full_response, tool_calls))
            messages.extend(tool_results)
            continue
        if finish_reason == "length":
            logger.info("%s response truncated (finish_reason=length), requesting continuation", ctx)
            truncated_text = full_response or ""
            truncated_prefix += truncated_text
            messages.append({"role": "assistant", "content": truncated_text})
            messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
            continue
        break

    final_text, thinking_block, display_final = build_final_display(
        final_response=(truncated_prefix + full_response if truncated_prefix else full_response),
        fallback_response=last_text_response,
        show_thinking=show_thinking,
        thinking_segments=thinking_segments,
        total_thinking_seconds=total_thinking_seconds,
        thinking_max_chars=SHOW_THINKING_MAX_CHARS,
    )
    if final_text == "(Empty response)":
        logger.warning("%s model returned empty visible response", ctx)
    return {
        "messages": messages,
        "final_text": final_text,
        "display_final": display_final,
        "thinking_block": thinking_block,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
    }
