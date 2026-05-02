"""Base message context for cross-platform handling."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseMessageContext(ABC):
    """Abstract base class for platform-specific message contexts.

    Provides a unified interface for command handlers and chat processing
    across Telegram, WeChat, and OneBot platforms.
    """

    @property
    @abstractmethod
    def local_user_id(self) -> int:
        """The user ID in the platform's native format."""
        pass

    @property
    @abstractmethod
    def local_chat_id(self) -> int:
        """The chat/conversation ID in the platform's native format."""
        pass

    @property
    @abstractmethod
    def is_group(self) -> bool:
        """Whether this message is from a group chat."""
        pass

    @property
    @abstractmethod
    def export_dir(self) -> str:
        """Directory for exported files."""
        pass

    @property
    def log_context(self) -> str:
        """Default log context string."""
        return f"[user:{self.local_user_id}]"

    @abstractmethod
    async def reply_text(self, text: str) -> None:
        """Send a text reply to the message."""
        pass

    @abstractmethod
    async def reply_file(self, file_path: str | Path, *, caption: str = "") -> None:
        """Send a file reply to the message."""
        pass

    async def send_private_text(self, text: str) -> None:
        """Send a private message to the user (optional)."""
        # Default implementation - platforms can override
        await self.reply_text(text)