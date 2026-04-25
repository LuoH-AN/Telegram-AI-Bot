"""Non-streaming response parsing for OpenAI chat completions."""

from __future__ import annotations

import logging
import time

from ai.types import StreamChunk, ToolCall

logger = logging.getLogger(__name__)


def build_nonstream_chunk(
    *,
    response,
    ctx_prefix: str,
    request_id: str,
    model: str,
    request_start: float,
) -> StreamChunk:
    choice = response.choices[0]
    content = choice.message.content
    prompt_tokens = response.usage.prompt_tokens if response.usage else 0
    completion_tokens = response.usage.completion_tokens if response.usage else 0

    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

    tool_calls: list[ToolCall] = []
    if choice.message.tool_calls:
        for tool_call in choice.message.tool_calls:
            tool_calls.append(
                ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                )
            )

    logger.info(
        "%sAI response done req=%s endpoint=chat.completions model=%s stream=false finish_reason=%s content_len=%d tool_calls=%d usage_prompt=%d usage_completion=%d latency_ms=%d",
        ctx_prefix,
        request_id,
        model,
        choice.finish_reason or "unknown",
        len(content or ""),
        len(tool_calls),
        prompt_tokens,
        completion_tokens,
        int((time.monotonic() - request_start) * 1000),
    )
    return StreamChunk(content=content, usage=usage, finished=True, tool_calls=tool_calls)
