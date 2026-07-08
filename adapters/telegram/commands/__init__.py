"""Telegram command handlers.

Commands self-register via ``@command`` decorators. ``discover()`` imports every
command module under this package, so adding a command is just adding a file —
no manual import list to maintain. ``app_builder`` builds ``CommandHandler``s
from ``all_commands()`` and ``/help`` renders from it.
"""

from .registry import CommandContext, all_commands, command, discover, get_command, make_handler

discover()

__all__ = ["CommandContext", "all_commands", "command", "discover", "get_command", "make_handler"]
