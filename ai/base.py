"""Abstract base class for AI clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Any


@dataclass
class ToolCall:
    """Represents a tool call from the model."""
    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class StreamChunk:
    """Represents a chunk from a streaming response."""
    content: str | None = None
    reasoning: str | None = None
    usage: dict | None = None
    finished: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


class AIClient(ABC):
    """Abstract base class for AI clients."""

    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        stream: bool = True,
        tools: list[dict] | None = None,
    ) -> Iterator[StreamChunk]:
        """Create a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use
            temperature: Temperature setting
            stream: Whether to stream the response
            tools: Optional list of tool definitions

        Yields:
            Stream chunks with content, usage info, and tool calls
        """
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models.

        Returns:
            List of model IDs
        """
        pass
