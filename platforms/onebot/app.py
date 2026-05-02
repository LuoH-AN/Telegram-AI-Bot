"""OneBot AI Bot entry point."""

from __future__ import annotations

import asyncio

from cache import init_database

from .config import ONEBOT_ENABLED, logger
from .group_config import load_group_modes
from .runtime import OneBotRuntime

__all__ = ["OneBotRuntime", "main"]


def main() -> None:
    if not ONEBOT_ENABLED:
        logger.error("ONEBOT_ENABLED is not enabled")
        return

    init_database()
    load_group_modes()

    logger.info("Starting OneBot/NapCat bot...")
    runtime = OneBotRuntime()
    asyncio.run(runtime.run())
