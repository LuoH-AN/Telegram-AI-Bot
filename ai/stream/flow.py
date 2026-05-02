"""Streaming response engine facade."""

from __future__ import annotations

from .live import stream_live_response
from .policy import should_update_stream as _should_update_stream
from .single import non_stream_response


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
    if stream_mode == "off":
        return await non_stream_response(
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
        )
    return await stream_live_response(
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
    )


__all__ = ["stream_response", "_should_update_stream"]
