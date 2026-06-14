"""Convenience re-exports for backward compatibility."""

from shared.utils.ai import (
    estimate_tokens,
    estimate_tokens_str,
    filter_thinking_content,
    extract_thinking_blocks,
    format_thinking_block,
    build_tool_status_text,
)
from shared.utils.stream import (
    ChatEventPump,
    ChatRenderEvent,
    StreamOutboundAdapter,
    send_message_safe,
    edit_message_safe,
)
from shared.utils.files import (
    get_file_extension,
    is_text_file,
    is_image_file,
    is_likely_text,
    decode_file_content,
    get_datetime_prompt,
)
from shared.utils.resolve import (
    resolve_provider_model,
)
from shared.utils.format import (
    build_rich_message,
    markdown_to_telegram_html,
    markdown_to_telegram_rich_markdown,
    should_use_rich_message,
    split_message,
    latex_to_unicode,
    html_to_markdown,
    strip_style_blocks,
)

__all__ = [
    # infrastructure.ai
    "estimate_tokens",
    "estimate_tokens_str",
    "filter_thinking_content",
    "extract_thinking_blocks",
    "format_thinking_block",
    "build_tool_status_text",
    # stream
    "ChatEventPump",
    "ChatRenderEvent",
    "StreamOutboundAdapter",
    "send_message_safe",
    "edit_message_safe",
    # files
    "get_file_extension",
    "is_text_file",
    "is_image_file",
    "is_likely_text",
    "decode_file_content",
    "get_datetime_prompt",
    # resolve
    "resolve_provider_model",
    # format
    "build_rich_message",
    "markdown_to_telegram_html",
    "markdown_to_telegram_rich_markdown",
    "should_use_rich_message",
    "split_message",
    "latex_to_unicode",
    "html_to_markdown",
    "strip_style_blocks",
]
