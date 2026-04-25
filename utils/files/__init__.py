"""File type detection and template helpers."""

from .detect import get_file_extension, is_text_file, is_image_file, is_likely_text, decode_file_content
from .template import get_datetime_prompt

__all__ = [
    "get_file_extension",
    "is_text_file",
    "is_image_file",
    "is_likely_text",
    "decode_file_content",
    "get_datetime_prompt",
]
