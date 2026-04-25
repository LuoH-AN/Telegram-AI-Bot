"""OneBot AI Bot entry point using modularized runtime parts."""

from __future__ import annotations

import asyncio
import threading

from cache import init_database
from services.platform import start_web_server

from .config import ONEBOT_ENABLED, logger
from .runtime import OneBotRuntime

__all__ = ["OneBotRuntime", "main"]


def main() -> None:
    if not ONEBOT_ENABLED:
        logger.error("ONEBOT_ENABLED is not enabled")
        return

    init_database()

    web_thread = threading.Thread(
        target=start_web_server,
        kwargs={"logger": logger},
        daemon=True,
    )
    web_thread.start()

    logger.info("Starting OneBot/NapCat bot...")
    runtime = OneBotRuntime()
    asyncio.run(runtime.run())
