"""OpenAI-compatible client package."""

from .client import OpenAIClient


def create_openai_client(api_key: str, base_url: str, log_context: str = "") -> OpenAIClient:
    return OpenAIClient(api_key=api_key, base_url=base_url, log_context=log_context)


__all__ = ["OpenAIClient", "create_openai_client"]
