"""Streaming response engine for AI chat.

Handles the real-time streaming of AI responses, updating output via
callback functions as chunks arrive. Tracks thinking/reasoning durations
and supports multiple stream update modes.
"""

import asyncio
import logging

from config import (
    STREAM_UPDATE_INTERVAL,
    STREAM_MIN_UPDATE_CHARS,
    STREAM_FORCE_UPDATE_INTERVAL,
    STREAM_TIME_MODE_INTERVAL,
    STREAM_CHARS_MODE_INTERVAL,
    AI_STREAM_INIT_TIMEOUT,
    AI_STREAM_NO_OUTPUT_TIMEOUT,
    AI_STREAM_OUTPUT_IDLE_TIMEOUT,
)
from utils import filter_thinking_content, extract_thinking_blocks, format_thinking_block

logger = logging.getLogger(__name__)

STREAM_BOUNDARY_CHARS = set(" \n\t.,!?;:)]}，。！？；：）】」》")


def _should_update_stream(
    mode: str, elapsed: float, new_chars: int, ends_with_boundary: bool,
) -> bool:
    """Determine if the streamed output should be pushed to the user."""
    if mode == "time":
        return elapsed >= STREAM_TIME_MODE_INTERVAL
    if mode == "chars":
        return new_chars >= STREAM_CHARS_MODE_INTERVAL
    return (
        (elapsed >= STREAM_UPDATE_INTERVAL and new_chars >= STREAM_MIN_UPDATE_CHARS)
        or (elapsed >= STREAM_UPDATE_INTERVAL and ends_with_boundary)
        or (elapsed >= STREAM_FORCE_UPDATE_INTERVAL)
    )


async def _non_stream_response(
    client,
    messages,
    model,
    temperature,
    reasoning_effort,
    stream_update,
    show_thinking,
    thinking_max_chars,
    tools,
):
    """Non-streaming response: wait for full response, deliver once."""
    loop = asyncio.get_event_loop()

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

    # Non-streaming returns a single chunk
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

    thinking_seconds = 0
    if full_reasoning and show_thinking:
        thinking_seconds = 1

    return full_response, usage_info, thinking_seconds, finish_reason, full_reasoning, tool_calls


async def stream_response(
    client,
    messages,
    model,
    temperature,
    reasoning_effort,
    stream_update,
    status_update=None,
    show_waiting=True,
    stream_mode="default",
    include_thought_prefix=True,
    stream_cursor=True,
    show_thinking=False,
    thinking_max_chars=1200,
    tools=None,
):
    """Stream an AI response, updating output in real-time.

    If stream_mode == "off", makes a single non-streaming request and delivers
    the full response at once (avoids rate-limit issues from frequent edits).
    """
    # Non-streaming path: single request, deliver full response at once
    if stream_mode == "off":
        return await _non_stream_response(
            client, messages, model, temperature, reasoning_effort,
            stream_update, show_thinking, thinking_max_chars, tools,
        )

    loop = asyncio.get_event_loop()
    status_cb = status_update or stream_update

    try:
        stream = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort or None,
                    stream=True,
                    tools=tools,
                ),
            ),
            timeout=AI_STREAM_INIT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("AI stream initialization timed out after %ds", AI_STREAM_INIT_TIMEOUT)
        return "", None, 0, "timeout", ""

    full_response = ""
    last_update_time = 0
    last_update_length = 0
    usage_info = None
    full_reasoning = ""
    tool_calls = []
    first_chunk = True
    finish_reason = None
    stream_start_time = loop.time()
    last_output_activity: float | None = None

    thinking_start_time = None
    thinking_seconds = 0
    thinking_locked = False

    waiting_start_time = loop.time()
    waiting_active = show_waiting

    def _build_thinking_block(seconds: int | None) -> str:
        if not show_thinking:
            return ""
        tag_thinking, _ = extract_thinking_blocks(full_response)
        combined = "\n\n".join(
            part for part in (full_reasoning.strip(), tag_thinking.strip()) if part
        ).strip()
        if not combined:
            return ""
        return format_thinking_block(
            combined,
            seconds=seconds,
            max_chars=thinking_max_chars,
        )

    def _build_thinking_status(seconds: int) -> str:
        block = _build_thinking_block(seconds)
        if block:
            return block
        return f"Thinking for {seconds}s"

    async def _update_waiting():
        try:
            while True:
                await asyncio.sleep(1)
                if not waiting_active:
                    break
                elapsed = max(1, int(loop.time() - waiting_start_time))
                await status_cb(_build_thinking_status(elapsed))
        except asyncio.CancelledError:
            pass

    waiting_task = asyncio.create_task(_update_waiting()) if show_waiting else None

    _end = object()
    it = iter(stream)

    try:
        while True:
            idle_limit = AI_STREAM_NO_OUTPUT_TIMEOUT if last_output_activity is None else AI_STREAM_OUTPUT_IDLE_TIMEOUT
            idle_since = stream_start_time if last_output_activity is None else last_output_activity
            timeout_left = idle_limit - (loop.time() - idle_since)
            if timeout_left <= 0:
                logger.warning(
                    "AI stream idle timeout (%ss, has_output=%s)",
                    idle_limit,
                    last_output_activity is not None,
                )
                finish_reason = finish_reason or "timeout"
                break
            try:
                chunk = await asyncio.wait_for(
                    loop.run_in_executor(None, next, it, _end),
                    timeout=max(1.0, timeout_left),
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "AI stream stalled: no activity for %ss (has_output=%s)",
                    idle_limit,
                    last_output_activity is not None,
                )
                finish_reason = finish_reason or "timeout"
                break

            if chunk is _end:
                break

            if chunk.usage is not None:
                usage_info = chunk.usage

            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)

            current_time = loop.time()
            has_output_activity = bool(chunk.content or chunk.reasoning)
            if has_output_activity:
                last_output_activity = current_time

            if chunk.reasoning:
                full_reasoning += chunk.reasoning
            if chunk.reasoning and thinking_start_time is None:
                waiting_active = False
                thinking_start_time = current_time
                thinking_seconds = 1
                await status_cb(_build_thinking_status(1))
                last_update_time = current_time

            if thinking_start_time is not None:
                new_seconds = max(1, int(current_time - thinking_start_time))
                display_text_now = filter_thinking_content(full_response, streaming=True) if full_response else ""
                if not display_text_now and new_seconds > thinking_seconds:
                    thinking_seconds = new_seconds
                    if current_time - last_update_time >= 1.0:
                        await status_cb(_build_thinking_status(thinking_seconds))
                        last_update_time = current_time

            if chunk.content:
                full_response += chunk.content

                display_text = filter_thinking_content(full_response, streaming=True)

                if not display_text and full_response.strip() and thinking_start_time is None:
                    waiting_active = False
                    thinking_start_time = current_time
                    thinking_seconds = 1
                    await status_cb(_build_thinking_status(1))
                    last_update_time = current_time

                thinking_prefix = ""
                if include_thought_prefix and thinking_start_time is not None and display_text:
                    if not thinking_locked:
                        thinking_seconds = max(1, int(current_time - thinking_start_time))
                        thinking_locked = True
                    thinking_prefix = f"_Thinking for {thinking_seconds}s_\n\n"
                thinking_block = _build_thinking_block(thinking_seconds if thinking_start_time else None)
                leading_block = thinking_block or thinking_prefix

                if first_chunk and display_text:
                    waiting_active = False
                    cursor_suffix = " ▌" if stream_cursor else ""
                    await stream_update(leading_block + display_text + cursor_suffix)
                    last_update_time = current_time
                    last_update_length = len(display_text)
                    first_chunk = False
                elif display_text and len(display_text) > last_update_length:
                    new_chars = len(display_text) - last_update_length
                    elapsed = current_time - last_update_time
                    ends_with_boundary = display_text[-1] in STREAM_BOUNDARY_CHARS

                    should_update = _should_update_stream(
                        stream_mode, elapsed, new_chars, ends_with_boundary,
                    )

                    if should_update:
                        cursor_suffix = " ▌" if stream_cursor else ""
                        await stream_update(leading_block + display_text + cursor_suffix)
                        last_update_time = current_time
                        last_update_length = len(display_text)

            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
    finally:
        waiting_active = False
        if waiting_task and not waiting_task.done():
            waiting_task.cancel()

    if thinking_start_time is not None and not thinking_locked:
        thinking_seconds = max(1, int(loop.time() - thinking_start_time))

    return full_response, usage_info, thinking_seconds, finish_reason, full_reasoning, tool_calls
