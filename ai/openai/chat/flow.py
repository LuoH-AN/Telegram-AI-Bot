"""Chat completion flow orchestration for OpenAI client."""
from __future__ import annotations
import logging
import time
import uuid
from typing import Iterator
from ai.base import StreamChunk

from .request import build_chat_kwargs, create_chat_response
from .single import build_nonstream_chunk
from .stream import StreamStats, iter_stream_chunks
from .utils import _find_last_user_preview, _role_summary

logger = logging.getLogger(__name__)

def run_chat_completion(
    *,
    client,
    base_host: str,
    ctx_prefix: str,
    messages: list[dict],
    model: str,
    temperature: float,
    reasoning_effort: str | None,
    stream: bool,
    tools: list[dict] | None,
) -> Iterator[StreamChunk]:
    request_id = uuid.uuid4().hex[:8]
    request_start = time.monotonic()
    logger.info(
        "%sAI request start req=%s endpoint=chat.completions model=%s stream=%s msgs=%d roles=%s tools=%d temp=%.2f reasoning_effort=%s base=%s last_user=%s",
        ctx_prefix,
        request_id,
        model,
        stream,
        len(messages),
        _role_summary(messages),
        len(tools or []),
        temperature,
        reasoning_effort or "-",
        base_host,
        _find_last_user_preview(messages),
    )
    kwargs = build_chat_kwargs(
        messages=messages,
        model=model,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        stream=stream,
        tools=tools,
    )
    response = create_chat_response(
        client=client,
        kwargs=kwargs,
        ctx_prefix=ctx_prefix,
        request_id=request_id,
        model=model,
        stream=stream,
        request_start=request_start,
    )
    if not stream:
        yield build_nonstream_chunk(
            response=response,
            ctx_prefix=ctx_prefix,
            request_id=request_id,
            model=model,
            request_start=request_start,
        )
        return

    stats = StreamStats()
    try:
        for chunk in iter_stream_chunks(response, stats):
            yield chunk
    except Exception:
        logger.exception(
            "%sAI stream failed req=%s endpoint=chat.completions model=%s chunks=%d latency_ms=%d",
            ctx_prefix,
            request_id,
            model,
            stats.chunk_count,
            int((time.monotonic() - request_start) * 1000),
        )
        raise

    logger.info(
        "%sAI response done req=%s endpoint=chat.completions model=%s stream=true chunks=%d finish_reason=%s content_chars=%d reasoning_chars=%d tool_calls=%d usage_prompt=%d usage_completion=%d latency_ms=%d",
        ctx_prefix,
        request_id,
        model,
        stats.chunk_count,
        stats.stream_finish_reason or "unknown",
        stats.content_chars,
        stats.reasoning_chars,
        stats.tool_call_count,
        stats.usage_prompt,
        stats.usage_completion,
        int((time.monotonic() - request_start) * 1000),
    )
