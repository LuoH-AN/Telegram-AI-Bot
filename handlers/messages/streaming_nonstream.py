"""Non-streaming response branch for stream_response()."""

from __future__ import annotations

import asyncio
import logging

from config import AI_STREAM_INIT_TIMEOUT

logger = logging.getLogger(__name__)


async def non_stream_response(
    client,
    messages,
    model,
    temperature,
    reasoning_effort,
    stream_update,
    status_update,
    show_waiting,
    show_thinking,
    thinking_max_chars,
    tools,
):
    del show_thinking, thinking_max_chars
    loop = asyncio.get_event_loop()
    status_cb = status_update or stream_update
    waiting_active = show_waiting

    async def _emit_waiting_notice() -> None:
        try:
            await asyncio.sleep(3)
            if waiting_active:
                await status_cb("Working...")
        except asyncio.CancelledError:
            pass

    waiting_task = asyncio.create_task(_emit_waiting_notice()) if show_waiting else None
    try:
        stream = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort or None,
                    stream=False,
                    tools=tools,
                ),
            ),
            timeout=AI_STREAM_INIT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("AI non-stream request timed out after %ds", AI_STREAM_INIT_TIMEOUT)
        return "", None, 0, "timeout", "", []
    finally:
        waiting_active = False
        if waiting_task and not waiting_task.done():
            waiting_task.cancel()

    full_response = ""
    usage_info = None
    full_reasoning = ""
    tool_calls = []
    finish_reason = None
    for chunk in stream:
        if chunk.content:
            full_response += chunk.content
        if chunk.reasoning:
            full_reasoning += chunk.reasoning
        if chunk.usage:
            usage_info = chunk.usage
        if chunk.tool_calls:
            tool_calls.extend(chunk.tool_calls)
        if chunk.finished:
            finish_reason = "stop"
    thinking_seconds = 1 if full_reasoning else 0
    return full_response, usage_info, thinking_seconds, finish_reason, full_reasoning, tool_calls
