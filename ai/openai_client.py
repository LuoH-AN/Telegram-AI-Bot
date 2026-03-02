"""OpenAI-compatible API client."""

import logging
import time
import uuid
from typing import Iterator
from urllib.parse import urlparse

from openai import OpenAI

from .base import AIClient, StreamChunk, ToolCall

logger = logging.getLogger(__name__)


def _shorten_text(text: str, limit: int = 120) -> str:
    """Return a single-line shortened string for logs."""
    normalized = (text or "").replace("\n", "\\n")
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "..."


def _preview_content(content: object, *, limit: int = 120) -> str:
    """Create a compact preview for message content in logs."""
    if content is None:
        return "(none)"
    if isinstance(content, str):
        stripped = content.strip()
        if not stripped:
            return "(empty)"
        return _shorten_text(stripped, limit)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content[:3]:
            if isinstance(item, dict):
                item_type = str(item.get("type", "unknown"))
                if item_type == "text":
                    text_part = str(item.get("text", "")).strip()
                    parts.append(f"text:{_shorten_text(text_part, 60) if text_part else '(empty)'}")
                else:
                    parts.append(item_type)
            else:
                parts.append(type(item).__name__)
        suffix = ", ..." if len(content) > 3 else ""
        return "[" + ", ".join(parts) + suffix + "]"
    return _shorten_text(str(content), limit)


def _role_summary(messages: list[dict]) -> str:
    """Build a role count summary like 'assistant:2,system:1,user:3'."""
    counts: dict[str, int] = {}
    for message in messages:
        role = "unknown"
        if isinstance(message, dict):
            role = str(message.get("role", "unknown"))
        counts[role] = counts.get(role, 0) + 1
    return ",".join(f"{role}:{counts[role]}" for role in sorted(counts)) if counts else "-"


def _find_last_user_preview(messages: list[dict]) -> str:
    """Return compact preview of the latest user message content."""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            return _preview_content(message.get("content"))
    return "(none)"


def _text_size(value: object) -> int:
    """Approximate text size for stream diagnostics."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    return len(str(value))


def _is_reasoning_param_error(error_text: str) -> bool:
    """Return True when provider rejects reasoning-specific parameters."""
    normalized = (error_text or "").lower()
    if "reasoning_effort" not in normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            "unsupported",
            "unknown",
            "unrecognized",
            "not allowed",
            "not supported",
            "extra inputs are not permitted",
            "unexpected keyword argument",
            "invalid parameter",
        )
    )


class OpenAIClient(AIClient):
    """OpenAI-compatible API client."""

    def __init__(self, api_key: str, base_url: str, log_context: str = ""):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.base_url = base_url
        parsed = urlparse(base_url or "")
        self.base_host = parsed.netloc or (base_url or "")
        self.log_context = (log_context or "").strip()

    def _ctx_prefix(self) -> str:
        """Return optional context prefix for log messages."""
        return f"{self.log_context} " if self.log_context else ""

    def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        reasoning_effort: str | None = None,
        stream: bool = True,
        tools: list[dict] | None = None,
    ) -> Iterator[StreamChunk]:
        """Create a chat completion with streaming and optional tools."""
        request_id = uuid.uuid4().hex[:8]
        request_start = time.monotonic()
        tools_count = len(tools or [])

        logger.info(
            "%sAI request start req=%s endpoint=chat.completions model=%s stream=%s msgs=%d roles=%s tools=%d temp=%.2f reasoning_effort=%s base=%s last_user=%s",
            self._ctx_prefix(),
            request_id,
            model,
            stream,
            len(messages),
            _role_summary(messages),
            tools_count,
            temperature,
            reasoning_effort or "-",
            self.base_host,
            _find_last_user_preview(messages),
        )

        # Build request kwargs
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        if stream:
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = tools

        while True:
            try:
                response = self.client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                err = str(e).lower()

                # If tools not supported by provider/model, retry without tools.
                # But never silently swallow invalid tool schema errors.
                has_tool_error = "tool" in err or "function" in err
                invalid_schema = (
                    "invalid_function_parameters" in err
                    or "invalid schema for function" in err
                    or "array schema missing items" in err
                )
                if "tools" in kwargs and has_tool_error and not invalid_schema:
                    logger.warning(
                        "%sAI request req=%s tools unsupported, retrying without tools: %s",
                        self._ctx_prefix(),
                        request_id,
                        _shorten_text(str(e), 280),
                    )
                    del kwargs["tools"]
                    continue

                # Some OpenAI-compatible providers reject reasoning_effort.
                if "reasoning_effort" in kwargs and _is_reasoning_param_error(err):
                    logger.warning(
                        "%sAI request req=%s reasoning_effort unsupported, retrying without reasoning_effort: %s",
                        self._ctx_prefix(),
                        request_id,
                        _shorten_text(str(e), 280),
                    )
                    del kwargs["reasoning_effort"]
                    continue

                logger.exception(
                    "%sAI request failed req=%s endpoint=chat.completions model=%s stream=%s latency_ms=%d",
                    self._ctx_prefix(),
                    request_id,
                    model,
                    stream,
                    int((time.monotonic() - request_start) * 1000),
                )
                raise

        if not stream:
            # Non-streaming response
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
            # Extract tool calls
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ))
            logger.info(
                "%sAI response done req=%s endpoint=chat.completions model=%s stream=false finish_reason=%s content_len=%d tool_calls=%d usage_prompt=%d usage_completion=%d latency_ms=%d",
                self._ctx_prefix(),
                request_id,
                model,
                choice.finish_reason or "unknown",
                len(content or ""),
                len(tool_calls),
                prompt_tokens,
                completion_tokens,
                int((time.monotonic() - request_start) * 1000),
            )
            yield StreamChunk(content=content, usage=usage, finished=True, tool_calls=tool_calls)
            return

        # Streaming response - collect tool calls across chunks
        tool_call_chunks: dict[int, dict] = {}  # index -> {id, name, arguments}
        chunk_count = 0
        content_chars = 0
        reasoning_chars = 0
        stream_finish_reason = None
        usage_prompt = 0
        usage_completion = 0

        try:
            for chunk in response:
                chunk_count += 1
                usage = None
                if hasattr(chunk, "usage") and chunk.usage is not None:
                    usage_prompt = chunk.usage.prompt_tokens or 0
                    usage_completion = chunk.usage.completion_tokens or 0
                    usage = {
                        "prompt_tokens": usage_prompt,
                        "completion_tokens": usage_completion,
                    }

                content = None
                reasoning = None
                delta = chunk.choices[0].delta if chunk.choices else None

                if delta and delta.content:
                    content = delta.content
                    content_chars += _text_size(content)

                # Capture reasoning/thinking content (e.g. DeepSeek R1)
                if delta:
                    rc = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if rc:
                        reasoning = rc
                        reasoning_chars += _text_size(reasoning)

                # Collect tool call deltas
                if delta and delta.tool_calls:
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
                finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                if finish_reason:
                    stream_finish_reason = finish_reason

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
                    yield StreamChunk(content=content, reasoning=reasoning, usage=usage, finished=finished, tool_calls=tool_calls, finish_reason=finish_reason)
        except Exception:
            logger.exception(
                "%sAI stream failed req=%s endpoint=chat.completions model=%s chunks=%d latency_ms=%d",
                self._ctx_prefix(),
                request_id,
                model,
                chunk_count,
                int((time.monotonic() - request_start) * 1000),
            )
            raise

        logger.info(
            "%sAI response done req=%s endpoint=chat.completions model=%s stream=true chunks=%d finish_reason=%s content_chars=%d reasoning_chars=%d tool_calls=%d usage_prompt=%d usage_completion=%d latency_ms=%d",
            self._ctx_prefix(),
            request_id,
            model,
            chunk_count,
            stream_finish_reason or "unknown",
            content_chars,
            reasoning_chars,
            len(tool_call_chunks),
            usage_prompt,
            usage_completion,
            int((time.monotonic() - request_start) * 1000),
        )

    def list_models(self) -> list[str]:
        """List available models."""
        request_id = uuid.uuid4().hex[:8]
        request_start = time.monotonic()
        logger.info(
            "%sAI request start req=%s endpoint=models.list base=%s",
            self._ctx_prefix(),
            request_id,
            self.base_host,
        )
        try:
            models = self.client.models.list()
            model_ids = sorted([m.id for m in models.data])
            logger.info(
                "%sAI response done req=%s endpoint=models.list count=%d latency_ms=%d",
                self._ctx_prefix(),
                request_id,
                len(model_ids),
                int((time.monotonic() - request_start) * 1000),
            )
            return model_ids
        except Exception:
            logger.exception(
                "%sAI request failed req=%s endpoint=models.list latency_ms=%d",
                self._ctx_prefix(),
                request_id,
                int((time.monotonic() - request_start) * 1000),
            )
            return []


def create_openai_client(api_key: str, base_url: str, log_context: str = "") -> OpenAIClient:
    """Create an OpenAI client instance."""
    return OpenAIClient(api_key=api_key, base_url=base_url, log_context=log_context)
