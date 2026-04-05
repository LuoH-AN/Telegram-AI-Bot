"""Logging service for AI interactions and errors."""

from .cleanup import delete_logs_filtered, keep_latest_logs
from .query import delete_log_by_id, get_user_logs
from .write import record_ai_interaction, record_error, record_terminal_command, record_web_action

__all__ = [
    "record_ai_interaction",
    "record_error",
    "record_web_action",
    "record_terminal_command",
    "get_user_logs",
    "delete_log_by_id",
    "delete_logs_filtered",
    "keep_latest_logs",
]

