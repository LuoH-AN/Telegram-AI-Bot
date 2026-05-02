"""Logging service for AI interactions and errors."""

from .write import record_ai_interaction, record_error, record_terminal_command

__all__ = [
    "record_ai_interaction",
    "record_error",
    "record_terminal_command",
]
