"""Log recording (re-exported from infrastructure.database.logging).

Recording is raw SQL writes to user_logs, an infrastructure concern. These
re-exports keep the historical ``from domain.services.log import ...`` imports
working; new callers should import from infrastructure.database.logging.
"""

from infrastructure.database.logging import (
    record_ai_interaction,
    record_error,
    record_terminal_command,
)

__all__ = [
    "record_ai_interaction",
    "record_error",
    "record_terminal_command",
]
