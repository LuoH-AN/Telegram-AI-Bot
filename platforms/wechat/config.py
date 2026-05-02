"""Shared config and logger setup for WeChat platform."""

from __future__ import annotations

import os

from config import HEALTH_CHECK_PORT
from platforms.shared.logging import setup_platform_logging
from utils.platform import format_log_context

logger = setup_platform_logging()

WECHAT_COMMAND_PREFIX = os.getenv("WECHAT_COMMAND_PREFIX", "/").strip() or "/"
WECHAT_STATE_DIR = os.getenv("WECHAT_STATE_DIR", "runtime/wechat").strip() or "runtime/wechat"
WECHAT_ENABLED = str(os.getenv("WECHAT_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
WECHAT_LOGIN_ACCESS_TOKEN = os.getenv("WECHAT_LOGIN_ACCESS_TOKEN", "").strip()
WECHAT_GROUP_REPLY_ALL = str(os.getenv("WECHAT_GROUP_REPLY_ALL", "")).strip().lower() in {"1", "true", "yes", "on"}
WECHAT_GROUP_MENTION_ALIASES = [
    item.strip()
    for item in os.getenv("WECHAT_GROUP_MENTION_ALIASES", "AI,ai,Bot,bot,助手,机器人,Gemen,gemen").split(",")
    if item.strip()
]
WECHAT_VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".mkv", ".avi")


def wechat_ctx(local_user_id: int) -> str:
    return format_log_context(platform="wechat", user_id=local_user_id, scope="private", chat_id=local_user_id)


def wechat_ctx_for_scope(*, local_user_id: int, local_chat_id: int, is_group: bool) -> str:
    return format_log_context(
        platform="wechat",
        user_id=local_user_id,
        scope="private",
        chat_id=local_chat_id,
    )


__all__ = [
    "logger",
    "HEALTH_CHECK_PORT",
    "WECHAT_COMMAND_PREFIX",
    "WECHAT_STATE_DIR",
    "WECHAT_ENABLED",
    "WECHAT_LOGIN_ACCESS_TOKEN",
    "WECHAT_GROUP_REPLY_ALL",
    "WECHAT_GROUP_MENTION_ALIASES",
    "WECHAT_VIDEO_SUFFIXES",
    "wechat_ctx",
    "wechat_ctx_for_scope",
]
