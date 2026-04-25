"""Per-chunk processing for live streaming responses."""

from __future__ import annotations

from utils import filter_thinking_content, extract_thinking_blocks, format_thinking_block

from .policy import STREAM_BOUNDARY_CHARS, should_update_stream


def build_thinking_block(full_response: str, full_reasoning: str, *, seconds: int | None, show_thinking: bool, max_chars: int) -> str:
    if not show_thinking:
        return ""
    tag_thinking, _ = extract_thinking_blocks(full_response)
    combined = "\n\n".join(part for part in (full_reasoning.strip(), tag_thinking.strip()) if part).strip()
    if not combined:
        return ""
    return format_thinking_block(combined, seconds=seconds, max_chars=max_chars)


def build_thinking_status(full_response: str, full_reasoning: str, *, seconds: int, show_thinking: bool, max_chars: int) -> str:
    block = build_thinking_block(full_response, full_reasoning, seconds=seconds, show_thinking=show_thinking, max_chars=max_chars)
    return block if block else f"Thinking for {seconds}s"


async def process_chunk(
    state,
    chunk,
    *,
    loop,
    stream_update,
    status_cb,
    stream_mode: str,
    include_thought_prefix: bool,
    stream_cursor: bool,
    show_thinking: bool,
    thinking_max_chars: int,
) -> None:
    if chunk.usage is not None:
        state.usage_info = chunk.usage
    if chunk.tool_calls:
        state.tool_calls.extend(chunk.tool_calls)

    now = loop.time()
    state.last_chunk_activity = now
    if chunk.content or chunk.reasoning:
        state.last_output_activity = now

    if chunk.reasoning:
        state.full_reasoning += chunk.reasoning
    if chunk.reasoning and state.thinking_start_time is None:
        state.waiting_active = False
        state.thinking_start_time = now
        state.thinking_seconds = 1
        await status_cb(build_thinking_status(state.full_response, state.full_reasoning, seconds=1, show_thinking=show_thinking, max_chars=thinking_max_chars))
        state.last_update_time = now

    if state.thinking_start_time is not None:
        new_seconds = max(1, int(now - state.thinking_start_time))
        display_now = filter_thinking_content(state.full_response, streaming=True) if state.full_response else ""
        if not display_now and new_seconds > state.thinking_seconds:
            state.thinking_seconds = new_seconds
            if now - state.last_update_time >= 1.0:
                await status_cb(build_thinking_status(state.full_response, state.full_reasoning, seconds=state.thinking_seconds, show_thinking=show_thinking, max_chars=thinking_max_chars))
                state.last_update_time = now

    if chunk.content:
        state.full_response += chunk.content
        display_text = filter_thinking_content(state.full_response, streaming=True)
        if not display_text and state.full_response.strip() and state.thinking_start_time is None:
            state.waiting_active = False
            state.thinking_start_time = now
            state.thinking_seconds = 1
            await status_cb(build_thinking_status(state.full_response, state.full_reasoning, seconds=1, show_thinking=show_thinking, max_chars=thinking_max_chars))
            state.last_update_time = now

        if include_thought_prefix and state.thinking_start_time is not None and display_text:
            if not state.thinking_locked:
                state.thinking_seconds = max(1, int(now - state.thinking_start_time))
                state.thinking_locked = True
            prefix = f"_Thinking for {state.thinking_seconds}s_\n\n"
        else:
            prefix = ""
        block = build_thinking_block(state.full_response, state.full_reasoning, seconds=state.thinking_seconds if state.thinking_start_time else None, show_thinking=show_thinking, max_chars=thinking_max_chars)
        leading = block or prefix

        if state.first_chunk and display_text:
            state.waiting_active = False
            await stream_update(leading + display_text + (" ▌" if stream_cursor else ""))
            state.last_update_time = now
            state.last_update_length = len(display_text)
            state.first_chunk = False
        elif display_text and len(display_text) > state.last_update_length:
            new_chars = len(display_text) - state.last_update_length
            elapsed = now - state.last_update_time
            if should_update_stream(stream_mode, elapsed, new_chars, display_text[-1] in STREAM_BOUNDARY_CHARS):
                await stream_update(leading + display_text + (" ▌" if stream_cursor else ""))
                state.last_update_time = now
                state.last_update_length = len(display_text)

    if chunk.finish_reason:
        state.finish_reason = chunk.finish_reason
