"""Shared cross-platform commands."""

from .account import export_command, usage_command
from .basic import (
    clear_command,
    help_command,
    restart_command,
    settings_command,
    start_command,
    stop_command,
    update_command,
)
from .chat import chat_command
from .memory import forget_command, memories_command, remember_command
from .persona import persona_command
from .settings import set_command

__all__ = [
    "start_command",
    "help_command",
    "clear_command",
    "stop_command",
    "update_command",
    "restart_command",
    "settings_command",
    "set_command",
    "usage_command",
    "export_command",
    "remember_command",
    "memories_command",
    "forget_command",
    "persona_command",
    "chat_command",
]
