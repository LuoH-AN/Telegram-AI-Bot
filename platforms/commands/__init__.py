"""Shared cross-platform commands."""

from .account import export_command, usage_command, web_command
from .basic import clear_command, help_command, settings_command, start_command, stop_command
from .dispatch import dispatch_command
from .memory import forget_command, memories_command, remember_command
from .persona_chat import chat_command, persona_command
from .settings_command import set_command

__all__ = [
    "start_command",
    "help_command",
    "clear_command",
    "stop_command",
    "settings_command",
    "set_command",
    "usage_command",
    "export_command",
    "remember_command",
    "memories_command",
    "forget_command",
    "persona_command",
    "chat_command",
    "web_command",
    "dispatch_command",
]
