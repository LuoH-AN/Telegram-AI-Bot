"""OpenAI-compatible API client implementation."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Iterator
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from infrastructure.ai.types import AIClient, StreamChunk

from .chat.flow import run_chat_completion
from .models import list_models_with_logging

logger = logging.getLogger(__name__)

# Bounds hung sockets so a stalled upstream surfaces instead of occupying a
# worker thread for the SDK's 600s default. read=180s > live.py's 120s output
# idle timeout, so graceful idle handling wins; this is only a backstop.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0)


class OpenAIClient(AIClient):
    def __init__(self, api_key: str, base_url: str, log_context: str = ""):
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=_HTTP_TIMEOUT)
        parsed = urlparse(base_url or "")
        self.base_host = parsed.netloc or (base_url or "")
        self.log_context = (log_context or "").strip()

    def _ctx_prefix(self) -> str:
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
        yield from run_chat_completion(
            client=self.client,
            base_host=self.base_host,
            ctx_prefix=self._ctx_prefix(),
            messages=messages,
            model=model,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            stream=stream,
            tools=tools,
        )

    def list_models(self) -> list[str]:
        request_id = uuid.uuid4().hex[:8]
        request_start = time.monotonic()
        ctx_prefix = self._ctx_prefix()
        logger.info(
            "%sAI request start req=%s endpoint=models.list base=%s",
            ctx_prefix,
            request_id,
            self.base_host,
        )
        return list_models_with_logging(
            client=self.client,
            ctx_prefix=ctx_prefix,
            request_id=request_id,
            request_start=request_start,
        )
