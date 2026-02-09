"""Gemini API client (placeholder for future implementation)."""

import logging
from typing import Iterator

from .base import AIClient, StreamChunk

logger = logging.getLogger(__name__)


class GeminiClient(AIClient):
    """Gemini API client.

    This is a placeholder implementation for future Gemini support.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        logger.warning("GeminiClient is not yet implemented")

    def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        stream: bool = True,
        tools: list[dict] | None = None,
    ) -> Iterator[StreamChunk]:
        """Create a chat completion.

        Not yet implemented.
        """
        raise NotImplementedError("Gemini support is not yet implemented")

    def list_models(self) -> list[str]:
        """List available models.

        Not yet implemented.
        """
        raise NotImplementedError("Gemini support is not yet implemented")


def create_gemini_client(api_key: str) -> GeminiClient:
    """Create a Gemini client instance."""
    return GeminiClient(api_key=api_key)
