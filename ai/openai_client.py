"""OpenAI-compatible API client."""

import logging
from typing import Iterator

from openai import OpenAI

from .base import AIClient, StreamChunk, ToolCall

logger = logging.getLogger(__name__)


class OpenAIClient(AIClient):
    """OpenAI-compatible API client."""

    def __init__(self, api_key: str, base_url: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        stream: bool = True,
        tools: list[dict] | None = None,
    ) -> Iterator[StreamChunk]:
        """Create a chat completion with streaming and optional tools."""
        # Build request kwargs
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if stream:
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            # If tools not supported, retry without tools
            if tools and ("tool" in str(e).lower() or "function" in str(e).lower()):
                logger.warning(f"Tools not supported, retrying without: {e}")
                del kwargs["tools"]
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise

        if not stream:
            # Non-streaming response
            choice = response.choices[0]
            content = choice.message.content
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }
            # Extract tool calls
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ))
            yield StreamChunk(content=content, usage=usage, finished=True, tool_calls=tool_calls)
            return

        # Streaming response - collect tool calls across chunks
        tool_call_chunks: dict[int, dict] = {}  # index -> {id, name, arguments}

        for chunk in response:
            usage = None
            if hasattr(chunk, "usage") and chunk.usage is not None:
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                }

            content = None
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content

            # Capture reasoning/thinking content (e.g. DeepSeek R1)
            reasoning = None
            if chunk.choices:
                delta = chunk.choices[0].delta
                rc = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                if rc:
                    reasoning = rc

            # Collect tool call deltas
            if chunk.choices and chunk.choices[0].delta.tool_calls:
                for tc_delta in chunk.choices[0].delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_chunks:
                        tool_call_chunks[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_call_chunks[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_call_chunks[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_call_chunks[idx]["arguments"] += tc_delta.function.arguments

            finished = chunk.choices[0].finish_reason is not None if chunk.choices else False

            # On finish, compile tool calls
            tool_calls = []
            if finished and tool_call_chunks:
                for idx in sorted(tool_call_chunks.keys()):
                    tc = tool_call_chunks[idx]
                    if tc["id"] and tc["name"]:
                        tool_calls.append(ToolCall(
                            id=tc["id"],
                            name=tc["name"],
                            arguments=tc["arguments"],
                        ))

            if content or reasoning or usage or finished:
                yield StreamChunk(content=content, reasoning=reasoning, usage=usage, finished=finished, tool_calls=tool_calls)

    def list_models(self) -> list[str]:
        """List available models."""
        try:
            models = self.client.models.list()
            return sorted([m.id for m in models.data])
        except Exception as e:
            logger.exception("Failed to fetch models")
            return []


def create_openai_client(api_key: str, base_url: str) -> OpenAIClient:
    """Create an OpenAI client instance."""
    return OpenAIClient(api_key=api_key, base_url=base_url)
