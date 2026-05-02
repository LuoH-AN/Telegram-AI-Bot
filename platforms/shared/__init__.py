"""Shared code for all platforms (Telegram, WeChat, OneBot)."""

from .cache import RecentKeyCache, NoopPump
from .logging import setup_platform_logging
from .context import BaseMessageContext
from .envelope import BaseInboundEnvelope

__all__ = [
    "RecentKeyCache",
    "NoopPump",
    "setup_platform_logging",
    "BaseMessageContext",
    "BaseInboundEnvelope",
]
