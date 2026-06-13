"""Telegram AI Bot entrypoint."""

from telegram import Update

from infrastructure.cache import init_database
from infrastructure.config import TELEGRAM_BOT_TOKEN

from .app_builder import build_application
from .logging_config import configure_platform_logging

logger = configure_platform_logging()


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    init_database()

    application = build_application(logger)
    logger.info("Starting bot...")
    from domain.services.cron import start_cron_scheduler

    start_cron_scheduler(application.bot)
    application.run_polling(allowed_updates=Update.ALL_TYPES)
