"""Launcher helpers for multi-platform runtime."""

from .bootstrap_cli import run_cli_bootstrap
from .env_helpers import apply_env_text, get_telegram_port, is_configured_token
from .process_helpers import (
    UPDATE_RESTART_EXIT_CODE,
    ChildProcess,
    start_child,
    terminate_children,
    wait_for_first_exit,
)

__all__ = [
    "UPDATE_RESTART_EXIT_CODE",
    "run_cli_bootstrap",
    "apply_env_text",
    "get_telegram_port",
    "is_configured_token",
    "ChildProcess",
    "start_child",
    "terminate_children",
    "wait_for_first_exit",
]
