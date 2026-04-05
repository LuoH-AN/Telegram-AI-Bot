"""Request construction and fallback retry logic for chat completions."""

from __future__ import annotations

import logging
import time

from .helpers import _is_reasoning_param_error, _shorten_text

logger = logging.getLogger(__name__)


def build_chat_kwargs(
    *,
    messages: list[dict],
    model: str,
    temperature: float,
    reasoning_effort: str | None,
    stream: bool,
    tools: list[dict] | None,
) -> dict:
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
    return kwargs


def create_chat_response(
    *,
    client,
    kwargs: dict,
    ctx_prefix: str,
    request_id: str,
    model: str,
    stream: bool,
    request_start: float,
):
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            err = str(exc).lower()
            has_tool_error = "tool" in err or "function" in err
            invalid_schema = (
                "invalid_function_parameters" in err
                or "invalid schema for function" in err
                or "array schema missing items" in err
            )
            if "tools" in kwargs and has_tool_error and not invalid_schema:
                logger.warning(
                    "%sAI request req=%s tools unsupported, retrying without tools: %s",
                    ctx_prefix,
                    request_id,
                    _shorten_text(str(exc), 280),
                )
                del kwargs["tools"]
                continue

            if "reasoning_effort" in kwargs and _is_reasoning_param_error(err):
                logger.warning(
                    "%sAI request req=%s reasoning_effort unsupported, retrying without reasoning_effort: %s",
                    ctx_prefix,
                    request_id,
                    _shorten_text(str(exc), 280),
                )
                del kwargs["reasoning_effort"]
                continue

            logger.exception(
                "%sAI request failed req=%s endpoint=chat.completions model=%s stream=%s latency_ms=%d",
                ctx_prefix,
                request_id,
                model,
                stream,
                int((time.monotonic() - request_start) * 1000),
            )
            raise
