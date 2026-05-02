"""WeChat AI Bot entry point."""

from __future__ import annotations

import asyncio

from cache import init_database

from .config import WECHAT_ENABLED, logger
from .runtime import WeChatBotRuntime

__all__ = ["WeChatBotRuntime", "main"]


def main() -> None:
    if not WECHAT_ENABLED:
        logger.error("WECHAT_ENABLED is not enabled")
        return

    init_database()

    logger.info("Starting WeChat bot...")
    runtime = WeChatBotRuntime()
    asyncio.run(runtime.run())
