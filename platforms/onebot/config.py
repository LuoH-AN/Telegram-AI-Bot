"""Shared config and logger setup for OneBot/QQ platform."""

from __future__ import annotations

import logging
import os

from config import HEALTH_CHECK_PORT
from utils.platform import format_log_context

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# OneBot/NapCat connection settings
ONEBOT_ENABLED = str(os.getenv("ONEBOT_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
ONEBOT_MODE = str(os.getenv("ONEBOT_MODE", "client")).strip().lower()  # "client" or "server"
# Client mode: we connect TO NapCat's WebSocket server
ONEBOT_WS_URL = os.getenv("ONEBOT_WS_URL", "ws://127.0.0.1:6099").strip()
ONEBOT_HTTP_URL = os.getenv("ONEBOT_HTTP_URL", "http://127.0.0.1:3000").strip()
# Server mode: we listen as WebSocket server for NapCat to connect to
# Port derived from ONEBOT_WS_URL for server mode (host:port)
ONEBOT_SERVER_HOST = os.getenv("ONEBOT_SERVER_HOST", "0.0.0.0").strip()
ONEBOT_SERVER_PORT = int(os.getenv("ONEBOT_SERVER_PORT", "8082").strip())
ONEBOT_ACCESS_TOKEN = os.getenv("ONEBOT_ACCESS_TOKEN", "").strip()

# QQ-specific settings
QQ_COMMAND_PREFIX = os.getenv("QQ_COMMAND_PREFIX", "/").strip() or "/"
QQ_STATE_DIR = os.getenv("QQ_STATE_DIR", "runtime/qq").strip() or "runtime/qq"
QQ_GROUP_REPLY_ALL = str(os.getenv("QQ_GROUP_REPLY_ALL", "")).strip().lower() in {"1", "true", "yes", "on"}
QQ_GROUP_MENTION_ALIASES = [
    item.strip()
    for item in os.getenv("QQ_GROUP_MENTION_ALIASES", "AI,ai,Bot,bot,助手,机器人").split(",")
    if item.strip()
]


def onebot_ctx(local_user_id: int) -> str:
    return format_log_context(platform="onebot", user_id=local_user_id, scope="private", chat_id=local_user_id)


def onebot_ctx_for_scope(*, local_user_id: int, local_chat_id: int, is_group: bool) -> str:
    return format_log_context(
        platform="onebot",
        user_id=local_user_id,
        scope="group" if is_group else "private",
        chat_id=local_chat_id,
    )


__all__ = [
    "logger",
    "HEALTH_CHECK_PORT",
    "ONEBOT_ENABLED",
    "ONEBOT_MODE",
    "ONEBOT_WS_URL",
    "ONEBOT_HTTP_URL",
    "ONEBOT_SERVER_HOST",
    "ONEBOT_SERVER_PORT",
    "ONEBOT_ACCESS_TOKEN",
    "QQ_COMMAND_PREFIX",
    "QQ_STATE_DIR",
    "QQ_GROUP_REPLY_ALL",
    "QQ_GROUP_MENTION_ALIASES",
    "onebot_ctx",
    "onebot_ctx_for_scope",
]
