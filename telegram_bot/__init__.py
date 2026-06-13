"""Telegram platform package."""

__all__ = ["main", "build_application", "configure_platform_logging"]


def main() -> None:
    """Entry point for Telegram platform."""
    from .app import main as _main
    _main()


def build_application(logger):
    """Build Telegram application."""
    from .app_builder import build_application as _build
    return _build(logger)


def configure_platform_logging():
    """Configure platform logging."""
    from .logging_config import configure_platform_logging as _configure
    _configure()