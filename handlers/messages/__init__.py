"""Message handlers module."""

from .text import chat
from .photo import handle_photo
from .document import handle_document

__all__ = [
    "chat",
    "handle_photo",
    "handle_document",
]
