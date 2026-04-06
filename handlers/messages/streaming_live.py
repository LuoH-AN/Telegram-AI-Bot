"""Live streaming branch for stream_response()."""

from __future__ import annotations

import asyncio
import logging

from config import AI_STREAM_INIT_TIMEOUT, AI_STREAM_NO_OUTPUT_TIMEOUT, AI_STREAM_OUTPUT_IDLE_TIMEOUT

from .rate_limit_retry import rate_limit_retry_delay_seconds
from .streaming_chunk import build_thinking_status, process_chunk
from .streaming_types import LiveStreamState

logger = logging.getLogger(__name__)


async def stream_live_response(
    client,
    messages,
    model,
    temperature,
    reasoning_effort,
    stream_update,
    status_update,
    show_waiting,
    stream_mode,
    include_thought_prefix,
    stream_cursor,
    show_thinking,
    thinking_max_chars,
    tools,
):
    loop = asyncio.get_event_loop()
    status_cb = status_update or stream_update
    stream = None
    for attempt in range(3):
        try:
            stream = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.chat_completion(messages=messages, model=model, temperature=temperature, reasoning_effort=reasoning_effort or None, stream=True, tools=tools),
                ),
                timeout=AI_STREAM_INIT_TIMEOUT,
            )
            break
        except asyncio.TimeoutError:
            logger.warning("AI stream initialization timed out after %ds", AI_STREAM_INIT_TIMEOUT)
            return "", None, 0, "timeout", "", []
        except Exception as exc:
            retry_after = rate_limit_retry_delay_seconds(exc)
            if retry_after is None or attempt >= 2:
                raise
            wait_for = max(1.0, min(12.0, float(retry_after)))
            logger.warning(
                "AI stream initialization rate limited, retrying in %.1fs (attempt %d/3): %s",
                wait_for,
                attempt + 1,
                exc,
            )
            await status_cb(f"Model rate limited. Retrying in {int(wait_for)}s...")
            await asyncio.sleep(wait_for)

    if stream is None:
        return "", None, 0, "error", "", []

    state = LiveStreamState(stream_start_time=loop.time(), waiting_start_time=loop.time(), waiting_active=show_waiting)

    async def _update_waiting():
        try:
            while True:
                await asyncio.sleep(1)
                if not state.waiting_active:
                    break
                seconds = max(1, int(loop.time() - state.waiting_start_time))
                await status_cb(build_thinking_status(state.full_response, state.full_reasoning, seconds=seconds, show_thinking=show_thinking, max_chars=thinking_max_chars))
        except asyncio.CancelledError:
            pass

    waiting_task = asyncio.create_task(_update_waiting()) if show_waiting else None
    end = object()
    it = iter(stream)
    try:
        while True:
            idle_limit = AI_STREAM_NO_OUTPUT_TIMEOUT if state.last_output_activity is None else AI_STREAM_OUTPUT_IDLE_TIMEOUT
            idle_since = state.stream_start_time if state.last_output_activity is None else state.last_output_activity
            timeout_left = idle_limit - (loop.time() - idle_since)
            if timeout_left <= 0:
                logger.warning("AI stream idle timeout (%ss, has_output=%s)", idle_limit, state.last_output_activity is not None)
                state.finish_reason = state.finish_reason or "timeout"
                break
            try:
                chunk = await asyncio.wait_for(loop.run_in_executor(None, next, it, end), timeout=max(1.0, timeout_left))
            except asyncio.TimeoutError:
                logger.warning("AI stream stalled: no activity for %ss (has_output=%s)", idle_limit, state.last_output_activity is not None)
                state.finish_reason = state.finish_reason or "timeout"
                break
            if chunk is end:
                break
            await process_chunk(
                state,
                chunk,
                loop=loop,
                stream_update=stream_update,
                status_cb=status_cb,
                stream_mode=stream_mode,
                include_thought_prefix=include_thought_prefix,
                stream_cursor=stream_cursor,
                show_thinking=show_thinking,
                thinking_max_chars=thinking_max_chars,
            )
    finally:
        state.waiting_active = False
        if waiting_task and not waiting_task.done():
            waiting_task.cancel()

    if state.thinking_start_time is not None and not state.thinking_locked:
        state.thinking_seconds = max(1, int(loop.time() - state.thinking_start_time))
    return state.full_response, state.usage_info, state.thinking_seconds, state.finish_reason, state.full_reasoning, state.tool_calls
