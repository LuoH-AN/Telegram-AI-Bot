"""Telegram platform package."""

from .app import main
from .app_builder import build_application
from .logging_config import configure_platform_logging

__all__ = ["main", "build_application", "configure_platform_logging"]
