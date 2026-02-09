"""AI client module with factory function."""

from services import get_user_settings
from .base import AIClient, StreamChunk, ToolCall
from .openai_client import OpenAIClient, create_openai_client
from .gemini_client import GeminiClient, create_gemini_client


def get_ai_client(user_id: int) -> AIClient:
    """Get an AI client for a user based on their settings.

    Currently only supports OpenAI-compatible APIs.
    """
    settings = get_user_settings(user_id)
    return create_openai_client(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
    )


# Backward compatibility alias
def get_openai_client(user_id: int) -> OpenAIClient:
    """Get an OpenAI client for a user."""
    settings = get_user_settings(user_id)
    return create_openai_client(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
    )


__all__ = [
    # Base
    "AIClient",
    "StreamChunk",
    "ToolCall",
    # OpenAI
    "OpenAIClient",
    "create_openai_client",
    # Gemini
    "GeminiClient",
    "create_gemini_client",
    # Factory
    "get_ai_client",
    "get_openai_client",
]
