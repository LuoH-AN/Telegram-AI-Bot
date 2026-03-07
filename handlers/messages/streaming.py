"""Streaming response engine for AI chat.

Handles the real-time streaming of AI responses, updating output via
callback functions as chunks arrive.  Tracks thinking/reasoning durations
and supports multiple stream update modes.
"""

import asyncio
import logging
import re

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
from utils import filter_thinking_content

logger = logging.getLogger(__name__)

# --- Streaming constants ---------------------------------------------------

STREAM_BOUNDARY_CHARS = set(" \n\t.,!?;:)]}，。！？；：）】」》")
SENTENCE_END_CHARS = set(".!?;:。！？；：…\n")


def stable_text_before_tool_call(text: str) -> str:
    """Return only stable/complete text before entering tool execution.

    Some models emit a partial sentence and immediately switch to tool_calls.
    This trims likely-incomplete tails so users don't see broken fragments.
    """
    candidate = (text or "").rstrip()
    if not candidate:
        return ""

    if candidate[-1] in SENTENCE_END_CHARS:
        return candidate

    last_break = -1
    for idx, ch in enumerate(candidate):
        if ch in SENTENCE_END_CHARS:
            last_break = idx

    if last_break >= 0:
        trimmed = candidate[: last_break + 1].rstrip()
        if len(trimmed) >= max(8, len(candidate) // 3):
            return trimmed

    # Keep very short updates only if they look like a complete phrase.
    if len(candidate) <= 12 and re.search(r"[。！？!?]$", candidate):
        return candidate
    return ""


async def stream_response(
    client,
    messages,
    model,
    temperature,
    reasoning_effort,
    tools,
    stream_update,
    status_update=None,
    show_waiting=True,
    stream_mode="default",
    include_thought_prefix=True,
    stream_cursor=True,
):
    """Stream an AI response, updating output in real-time.

    The synchronous OpenAI streaming iterator is wrapped with run_in_executor
    so that waiting for each chunk does not block the async event loop.

    Args:
        show_waiting: Show "Think for Xs" waiting indicator.  Set to False
                      on subsequent tool rounds to reduce Telegram message edits.
        stream_mode: Update mode for streaming:
                     - "default": original behavior (time + chars conditions)
                     - "time": update every second regardless of chars
                     - "chars": update every 100 chars regardless of time

    Returns:
        (full_response, usage_info, all_tool_calls, thinking_seconds, finish_reason)
    """
    loop = asyncio.get_event_loop()
    status_cb = status_update or stream_update

    # Start the streaming request in a thread to avoid blocking
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
        return "", None, [], 0, "timeout"

    full_response = ""
    last_update_time = 0
    last_update_length = 0
    usage_info = None
    all_tool_calls = []
    first_chunk = True
    finish_reason = None
    stream_start_time = loop.time()
    last_output_activity: float | None = None

    # Thinking/reasoning tracking
    thinking_start_time = None
    thinking_seconds = 0
    thinking_locked = False

    # Generic waiting indicator ("Think for Xs" before content/reasoning arrives)
    waiting_start_time = loop.time()
    waiting_active = show_waiting

    async def _update_waiting():
        try:
            while True:
                await asyncio.sleep(1)
                if not waiting_active:
                    break
                elapsed = max(1, int(loop.time() - waiting_start_time))
                await status_cb(f"Think for {elapsed}s")
        except asyncio.CancelledError:
            pass

    waiting_task = asyncio.create_task(_update_waiting()) if show_waiting else None

    # Use a sentinel to detect end of iterator without StopIteration
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

            current_time = loop.time()
            has_output_activity = bool(chunk.content or chunk.reasoning or chunk.tool_calls)
            if has_output_activity:
                last_output_activity = current_time

            # Detect thinking/reasoning (separate field, e.g. DeepSeek R1)
            if chunk.reasoning and thinking_start_time is None:
                waiting_active = False
                thinking_start_time = current_time
                thinking_seconds = 1
                await status_cb("Thought for 1s")
                last_update_time = current_time

            # Update thinking counter while still in thinking phase
            if thinking_start_time is not None:
                new_seconds = max(1, int(current_time - thinking_start_time))
                display_text_now = filter_thinking_content(full_response, streaming=True) if full_response else ""
                if not display_text_now and new_seconds > thinking_seconds:
                    thinking_seconds = new_seconds
                    if current_time - last_update_time >= 1.0:
                        await status_cb(f"Thought for {thinking_seconds}s")
                        last_update_time = current_time

            if chunk.content:
                full_response += chunk.content

                display_text = filter_thinking_content(full_response, streaming=True)

                # Detect thinking via <think> tags in content
                if not display_text and full_response.strip() and thinking_start_time is None:
                    waiting_active = False
                    thinking_start_time = current_time
                    thinking_seconds = 1
                    await status_cb("Thought for 1s")
                    last_update_time = current_time

                # Build thinking prefix for display
                thinking_prefix = ""
                if include_thought_prefix and thinking_start_time is not None and display_text:
                    # Lock thinking duration when visible content first appears.
                    # Do not keep extending it while normal content continues streaming.
                    if not thinking_locked:
                        thinking_seconds = max(1, int(current_time - thinking_start_time))
                        thinking_locked = True
                    thinking_prefix = f"_Thought for {thinking_seconds}s_\n\n"

                # First visible chunk: update immediately, skip throttle interval
                if first_chunk and display_text:
                    waiting_active = False
                    cursor_suffix = " ▌" if stream_cursor else ""
                    await stream_update(thinking_prefix + display_text + cursor_suffix)
                    last_update_time = current_time
                    last_update_length = len(display_text)
                    first_chunk = False
                elif display_text and len(display_text) > last_update_length:
                    new_chars = len(display_text) - last_update_length
                    elapsed = current_time - last_update_time
                    ends_with_boundary = display_text[-1] in STREAM_BOUNDARY_CHARS

                    # Determine if we should update based on stream_mode
                    if stream_mode == "time":
                        # Time mode: update every STREAM_TIME_MODE_INTERVAL seconds
                        should_update = elapsed >= STREAM_TIME_MODE_INTERVAL
                    elif stream_mode == "chars":
                        # Chars mode: update every STREAM_CHARS_MODE_INTERVAL characters
                        should_update = new_chars >= STREAM_CHARS_MODE_INTERVAL
                    else:
                        # Default mode: original behavior (time + chars OR force update)
                        should_update = (
                            (elapsed >= STREAM_UPDATE_INTERVAL and new_chars >= STREAM_MIN_UPDATE_CHARS)
                            or (elapsed >= STREAM_UPDATE_INTERVAL and ends_with_boundary)
                            or (elapsed >= STREAM_FORCE_UPDATE_INTERVAL)
                        )

                    if should_update:
                        cursor_suffix = " ▌" if stream_cursor else ""
                        await stream_update(thinking_prefix + display_text + cursor_suffix)
                        last_update_time = current_time
                        last_update_length = len(display_text)

            if chunk.tool_calls:
                all_tool_calls.extend(chunk.tool_calls)

            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
    finally:
        # Clean up waiting indicator
        waiting_active = False
        if waiting_task and not waiting_task.done():
            waiting_task.cancel()

    # Finalize thinking seconds at stream end only if no visible content ever appeared.
    if thinking_start_time is not None and not thinking_locked:
        thinking_seconds = max(1, int(loop.time() - thinking_start_time))

    return full_response, usage_info, all_tool_calls, thinking_seconds, finish_reason
