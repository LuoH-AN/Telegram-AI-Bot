"""Media message handlers."""

from .document import handle_document
from .photo import handle_photo

__all__ = ["handle_photo", "handle_document"]
