"""AI client module with factory function."""

from services import get_user_settings
from .types import AIClient, StreamChunk, ToolCall
from .openai import OpenAIClient, create_openai_client


def get_ai_client(user_id: int) -> AIClient:
    settings = get_user_settings(user_id)
    return create_openai_client(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        log_context=f"[user={user_id}]",
    )


__all__ = [
    "AIClient",
    "StreamChunk",
    "ToolCall",
    "OpenAIClient",
    "create_openai_client",
    "get_ai_client",
]
