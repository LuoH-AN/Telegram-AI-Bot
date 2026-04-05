"""Backwards-compatible terminal execution exports."""

from .core import execute_terminal_command
from .shared import DEFAULT_TIMEOUT_SECONDS, MAX_OUTPUT_CHARS, REPO_ROOT

__all__ = [
    "REPO_ROOT",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_OUTPUT_CHARS",
    "execute_terminal_command",
]

