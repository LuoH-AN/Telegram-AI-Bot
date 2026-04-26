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

    # Create runtime BEFORE starting the web server so that
    # the FastAPI /onebot/ws endpoint can reference it when
    # NapCat connects before the main thread reaches runtime.run()
    logger.info("Starting OneBot/NapCat bot...")
    runtime = OneBotRuntime()

    web_thread = threading.Thread(
        target=start_web_server,
        kwargs={"logger": logger},
        daemon=True,
    )
    web_thread.start()

    asyncio.run(runtime.run())
