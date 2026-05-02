"""WeChat platform package."""

__all__ = ["main", "WeChatBotRuntime"]


def main() -> None:
    """Entry point for WeChat platform."""
    from .app import main as _main
    _main()