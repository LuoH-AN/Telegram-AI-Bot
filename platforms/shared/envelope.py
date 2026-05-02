"""Base inbound envelope for cross-platform message handling."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BaseInboundEnvelope(ABC):
    """Abstract base class for inbound message envelopes.

    Provides a unified interface for message data across platforms.
    Each platform implements its own envelope with platform-specific fields.
    """

    @property
    @abstractmethod
    def message(self) -> Any:
        """The raw message object from the platform."""
        pass

    @property
    @abstractmethod
    def inbound_key(self) -> str | None:
        """Unique key for deduplication."""
        pass

    @property
    @abstractmethod
    def from_user_id(self) -> str:
        """Sender's user ID as string."""
        pass

    @property
    @abstractmethod
    def to_user_id(self) -> str:
        """Recipient's user ID as string."""
        pass

    @property
    @abstractmethod
    def group_id(self) -> str | None:
        """Group ID if this is a group message, None otherwise."""
        pass

    @property
    @abstractmethod
    def reply_to_id(self) -> str:
        """ID to reply to (message or conversation)."""
        pass

    @property
    @abstractmethod
    def text_body(self) -> str:
        """The text content of the message."""
        pass

    @property
    @abstractmethod
    def normalized_text(self) -> str:
        """Normalized text for processing (lowercase, trimmed, etc.)."""
        pass

    @property
    @abstractmethod
    def is_group(self) -> bool:
        """Whether this message is from a group chat."""
        pass

    @property
    @abstractmethod
    def echo_target_id(self) -> str:
        """Target ID for echo suppression."""
        pass
