"""Shared code for all platforms (Telegram, WeChat, OneBot)."""

from .cache import RecentKeyCache, NoopPump
from .logging import setup_platform_logging
from .context import BaseMessageContext
from .envelope import BaseInboundEnvelope
from .prompt_upload import (
    PROMPT_TARGET_GLOBAL,
    PROMPT_TARGET_PERSONA,
    PromptUploadCommand,
    apply_prompt_upload,
    parse_prompt_upload_caption,
)

__all__ = [
    "RecentKeyCache",
    "NoopPump",
    "setup_platform_logging",
    "BaseMessageContext",
    "BaseInboundEnvelope",
    "PromptUploadCommand",
    "parse_prompt_upload_caption",
    "apply_prompt_upload",
    "PROMPT_TARGET_PERSONA",
    "PROMPT_TARGET_GLOBAL",
]
