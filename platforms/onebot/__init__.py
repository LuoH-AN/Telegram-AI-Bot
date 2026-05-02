"""OneBot platform package."""

__all__ = ["main", "OneBotRuntime"]


def main() -> None:
    """Entry point for OneBot platform."""
    from .app import main as _main
    _main()