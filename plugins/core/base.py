"""Base class for plugins."""

from abc import ABC, abstractmethod


class BasePlugin(ABC):
    """Abstract base class for plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier for this plugin."""

    @abstractmethod
    def definitions(self) -> list[dict]:
        """Return OpenAI function-calling format tool definitions."""

    @abstractmethod
    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        """Execute a tool call, return result text (or None)."""

    def get_instruction(self) -> str:
        """Extra instruction appended to system prompt. Default empty."""
        return ""

    def enrich_system_prompt(self, user_id: int, system_prompt: str, **kwargs) -> str:
        """Inject context into system prompt. Default no-op."""
        return system_prompt

    def post_process(self, user_id: int, text: str) -> str:
        """Post-process AI response text. Default no-op."""
        return text


# Backwards alias
BaseTool = BasePlugin
