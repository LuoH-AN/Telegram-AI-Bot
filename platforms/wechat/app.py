"""WeChat AI Bot entry point using modularized runtime parts."""

from __future__ import annotations

import asyncio
import threading

from cache import init_database
from services.platform import start_web_server

from .config import WECHAT_ENABLED, logger
from .runtime import WeChatBotRuntime

__all__ = ["WeChatBotRuntime", "main"]


def main() -> None:
    if not WECHAT_ENABLED:
        logger.error("WECHAT_ENABLED is not enabled")
        return

    init_database()

    web_thread = threading.Thread(
        target=start_web_server,
        kwargs={"logger": logger},
        daemon=True,
    )
    web_thread.start()

    logger.info("Starting WeChat bot...")
    runtime = WeChatBotRuntime()
    asyncio.run(runtime.run())
