"""Logging configuration for Telegram runtime."""

import logging


def configure_platform_logging() -> logging.Logger:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logger = logging.getLogger("adapters.telegram")
    for name in ("httpx", "httpcore", "telegram", "openai", "uvicorn", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return logger
