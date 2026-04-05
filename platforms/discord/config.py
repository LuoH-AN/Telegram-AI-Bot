"""Discord config and logger shared across modules."""

from __future__ import annotations

import logging

from config import (
    DISCORD_API_BASE,
    DISCORD_BOT_TOKEN,
    DISCORD_CDN_BASE,
    DISCORD_COMMAND_PREFIX,
    DISCORD_GATEWAY_BASE,
    DISCORD_INVITE_BASE,
    HEALTH_CHECK_PORT,
    MAX_FILE_SIZE,
    MAX_TEXT_CONTENT_LENGTH,
    MIME_TYPE_MAP,
    SHOW_THINKING_MAX_CHARS,
    STREAM_CHARS_MODE_INTERVAL,
    STREAM_FORCE_UPDATE_INTERVAL,
    STREAM_MIN_UPDATE_CHARS,
    STREAM_TIME_MODE_INTERVAL,
    STREAM_UPDATE_INTERVAL,
    STREAM_UPDATE_MODE,
    VALID_REASONING_EFFORTS,
    WEB_BASE_URL,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

DISCORD_MAX_MESSAGE_LENGTH = 2000
TOOL_TIMEOUT = 30
AI_STREAM_NO_OUTPUT_TIMEOUT = 45
AI_STREAM_OUTPUT_IDLE_TIMEOUT = 120
STREAM_BOUNDARY_CHARS = set(" \n\t.,!?;:)]}，。！？；：）】」》")
STREAM_PREVIEW_PREFIX = "[...]\n"

__all__ = [
    "DISCORD_BOT_TOKEN",
    "DISCORD_COMMAND_PREFIX",
    "DISCORD_API_BASE",
    "DISCORD_GATEWAY_BASE",
    "DISCORD_CDN_BASE",
    "DISCORD_INVITE_BASE",
    "HEALTH_CHECK_PORT",
    "STREAM_UPDATE_INTERVAL",
    "STREAM_MIN_UPDATE_CHARS",
    "STREAM_FORCE_UPDATE_INTERVAL",
    "STREAM_UPDATE_MODE",
    "STREAM_TIME_MODE_INTERVAL",
    "STREAM_CHARS_MODE_INTERVAL",
    "MAX_FILE_SIZE",
    "MAX_TEXT_CONTENT_LENGTH",
    "MIME_TYPE_MAP",
    "WEB_BASE_URL",
    "SHOW_THINKING_MAX_CHARS",
    "VALID_REASONING_EFFORTS",
    "DISCORD_MAX_MESSAGE_LENGTH",
    "TOOL_TIMEOUT",
    "AI_STREAM_NO_OUTPUT_TIMEOUT",
    "AI_STREAM_OUTPUT_IDLE_TIMEOUT",
    "STREAM_BOUNDARY_CHARS",
    "STREAM_PREVIEW_PREFIX",
    "logger",
]
