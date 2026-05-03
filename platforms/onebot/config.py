"""Shared config and logger setup for OneBot/QQ platform."""

from __future__ import annotations

import os

from platforms.shared.logging import setup_platform_logging
from utils.platform import format_log_context

logger = setup_platform_logging()

# OneBot/NapCat connection settings
ONEBOT_ENABLED = str(os.getenv("ONEBOT_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
# Connection mode:
#   "client"      - we connect to NapCat's WebSocket server (NapCat = server)
#   "server"      - we run as WebSocket server, NapCat connects to us (NapCat = client)
#   "ws"          - standalone WebSocket server, NapCat reverse-connects to /onebot/ws
ONEBOT_MODE = str(os.getenv("ONEBOT_MODE", "client")).strip().lower()
# Client mode: we connect TO NapCat's WebSocket server
ONEBOT_WS_URL = os.getenv("ONEBOT_WS_URL", "ws://127.0.0.1:6099").strip()
ONEBOT_HTTP_URL = os.getenv("ONEBOT_HTTP_URL", "http://127.0.0.1:3000").strip()
# Server/WS mode: we listen as WebSocket server
# ONEBOT_SERVER_HOST and ONEBOT_SERVER_PORT used by "server" mode
ONEBOT_SERVER_HOST = os.getenv("ONEBOT_SERVER_HOST", "0.0.0.0").strip()
ONEBOT_SERVER_PORT = int(os.getenv("ONEBOT_SERVER_PORT", "8082").strip())
# WS mode: standalone reverse-WS server
ONEBOT_WS_BIND_HOST = os.getenv("ONEBOT_WS_BIND_HOST", "0.0.0.0").strip()
ONEBOT_WS_BIND_PORT = int(os.getenv("ONEBOT_WS_BIND_PORT", os.getenv("PORT", "7864")).strip())
ONEBOT_WS_PATH = os.getenv("ONEBOT_WS_PATH", "/onebot/ws").strip() or "/onebot/ws"
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
QQ_ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("QQ_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
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
    "ONEBOT_ENABLED",
    "ONEBOT_MODE",
    "ONEBOT_WS_URL",
    "ONEBOT_HTTP_URL",
    "ONEBOT_SERVER_HOST",
    "ONEBOT_SERVER_PORT",
    "ONEBOT_WS_BIND_HOST",
    "ONEBOT_WS_BIND_PORT",
    "ONEBOT_WS_PATH",
    "ONEBOT_ACCESS_TOKEN",
    "QQ_COMMAND_PREFIX",
    "QQ_STATE_DIR",
    "QQ_GROUP_REPLY_ALL",
    "QQ_GROUP_MENTION_ALIASES",
    "QQ_ADMIN_IDS",
    "onebot_ctx",
    "onebot_ctx_for_scope",
]
