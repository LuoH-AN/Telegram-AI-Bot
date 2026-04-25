"""Streaming response parsing for OpenAI chat completions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ai.base import StreamChunk, ToolCall

from .utils import _text_size


@dataclass
class StreamStats:
    chunk_count: int = 0
    content_chars: int = 0
    reasoning_chars: int = 0
    stream_finish_reason: str | None = None
    usage_prompt: int = 0
    usage_completion: int = 0
    tool_call_count: int = 0


def iter_stream_chunks(response, stats: StreamStats) -> Iterator[StreamChunk]:
    tool_call_chunks: dict[int, dict] = {}
    for chunk in response:
        stats.chunk_count += 1
        usage = None
        if hasattr(chunk, "usage") and chunk.usage is not None:
            stats.usage_prompt = chunk.usage.prompt_tokens or 0
            stats.usage_completion = chunk.usage.completion_tokens or 0
            usage = {
                "prompt_tokens": stats.usage_prompt,
                "completion_tokens": stats.usage_completion,
            }

        content = None
        reasoning = None
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            content = delta.content
            stats.content_chars += _text_size(content)

        if delta:
            rc = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if rc:
                reasoning = rc
                stats.reasoning_chars += _text_size(reasoning)

        if delta and delta.tool_calls:
            for tool_delta in chunk.choices[0].delta.tool_calls:
                idx = tool_delta.index
                if idx not in tool_call_chunks:
                    tool_call_chunks[idx] = {"id": "", "name": "", "arguments": ""}
                if tool_delta.id:
                    tool_call_chunks[idx]["id"] = tool_delta.id
                if tool_delta.function:
                    if tool_delta.function.name:
                        tool_call_chunks[idx]["name"] = tool_delta.function.name
                    if tool_delta.function.arguments:
                        tool_call_chunks[idx]["arguments"] += tool_delta.function.arguments

        finished = chunk.choices[0].finish_reason is not None if chunk.choices else False
        finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
        if finish_reason:
            stats.stream_finish_reason = finish_reason

        tool_calls: list[ToolCall] = []
        if finished and tool_call_chunks:
            for idx in sorted(tool_call_chunks.keys()):
                tc = tool_call_chunks[idx]
                if tc["id"] and tc["name"]:
                    tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"]))
            stats.tool_call_count = len(tool_call_chunks)

        if content or reasoning or usage or finished:
            yield StreamChunk(
                content=content,
                reasoning=reasoning,
                usage=usage,
                finished=finished,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
