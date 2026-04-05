"""Telegram AI Bot entrypoint."""

import threading

from telegram import Update

from cache import init_database
from config import HEALTH_CHECK_PORT, TELEGRAM_BOT_TOKEN
from platforms.telegram_runtime import build_application, configure_platform_logging
from services.platform_shared import start_web_server

logger = configure_platform_logging()


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    init_database()
    threading.Thread(
        target=start_web_server,
        kwargs={"logger": logger, "port": HEALTH_CHECK_PORT},
        daemon=True,
    ).start()

    application = build_application(logger)
    logger.info("Starting bot...")
    from services.cron import start_cron_scheduler

    start_cron_scheduler(application.bot)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
