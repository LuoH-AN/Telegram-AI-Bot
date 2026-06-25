"""Telegram command handlers.

Importing this package imports every command module, which registers each
command with the registry via its ``@command`` decorator. ``app_builder`` then
builds ``CommandHandler``s from ``all_commands()`` and ``/help`` renders from it.
"""

from .registry import all_commands, command

# Importing these registers their commands (side effect of @command decorators).
# Import order sets the /help listing order (registration order).
from . import (  # noqa: F401
    basic,
    persona,
    chat,
    settings,
    lifecycle,
    memory,
    usage,
    status,
    skill,
)

__all__ = ["all_commands", "command"]
