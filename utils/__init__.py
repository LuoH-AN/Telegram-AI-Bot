"""Utility functions module."""

from .filters import (
    filter_thinking_content,
    parse_raw_tool_calls,
    extract_thinking_blocks,
    format_thinking_block,
)
from .formatters import (
    markdown_to_telegram_html,
    split_message,
    latex_to_unicode,
    html_to_markdown,
    strip_style_blocks,
)
from .telegram import send_message_safe, edit_message_safe
from .template import get_datetime_prompt
from .chat_events import ChatRenderEvent, ChatEventPump
from .outbound import StreamOutboundAdapter
from .files import (
    get_file_extension,
    is_text_file,
    is_image_file,
    is_likely_text,
    decode_file_content,
)
from .provider import resolve_provider_model

__all__ = [
    # Filters
    "filter_thinking_content",
    "parse_raw_tool_calls",
    "extract_thinking_blocks",
    "format_thinking_block",
    # Formatters
    "markdown_to_telegram_html",
    "split_message",
    "latex_to_unicode",
    "html_to_markdown",
    "strip_style_blocks",
    # Telegram
    "send_message_safe",
    "edit_message_safe",
    # Template
    "get_datetime_prompt",
    # Chat stream events/outbound
    "ChatRenderEvent",
    "ChatEventPump",
    "StreamOutboundAdapter",
    # Files
    "get_file_extension",
    "is_text_file",
    "is_image_file",
    "is_likely_text",
    "decode_file_content",
    # Provider resolution
    "resolve_provider_model",
]
