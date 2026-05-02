"""Shared logging configuration for platforms."""

from __future__ import annotations

import logging


def setup_platform_logging() -> logging.Logger:
    """Set up consistent logging for platform modules.

    Configures the root logger and suppresses verbose third-party logs.
    Returns a logger for the calling module.
    """
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Suppress verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return logging.getLogger(__name__)
