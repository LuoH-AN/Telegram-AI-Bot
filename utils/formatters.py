"""Text formatting utilities."""

import html
import re

from config import MAX_MESSAGE_LENGTH


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML.

    Handles common Markdown syntax and converts to HTML that Telegram supports:
    - Headers: # text -> <b>text</b> (Telegram doesn't support h1-h6)
    - Horizontal rules: --- or *** or ___ -> ──────────
    - Unordered lists: - item / * item / + item -> • item
    - Ordered lists: 1. item (normalized spacing)
    - Bold: **text** or __text__ -> <b>text</b>
    - Italic: *text* or _text_ -> <i>text</i>
    - Code: `code` -> <code>code</code>
    - Code blocks: ```code``` -> <pre>code</pre>
    - Strikethrough: ~~text~~ -> <s>text</s>
    - Links: [text](url) -> <a href="url">text</a>
    """
    if not text:
        return text

    # First, escape HTML special characters in the original text
    # But we need to be careful not to escape our converted HTML tags
    # So we'll process step by step

    # Store code blocks and inline code to protect them from other processing
    code_blocks = []
    inline_codes = []

    # Extract code blocks first (```...```)
    def save_code_block(match):
        code_blocks.append(match.group(1) or match.group(2))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    # Match ```lang\ncode``` or ```code```
    text = re.sub(r'```(?:\w*\n)?(.*?)```|```(.*?)```', save_code_block, text, flags=re.DOTALL)

    # Extract inline code (`...`)
    def save_inline_code(match):
        inline_codes.append(match.group(1))
        return f"\x00INLINECODE{len(inline_codes) - 1}\x00"

    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # Convert headers BEFORE escaping (# won't be escaped anyway)
    # Headers: # text, ## text, etc. -> bold text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', text, flags=re.MULTILINE)

    # Convert horizontal rules BEFORE escaping
    # ---, ***, ___ (3 or more) -> unicode line
    text = re.sub(r'^[-*_]{3,}\s*$', '──────────', text, flags=re.MULTILINE)

    # Convert lists BEFORE escaping
    # Unordered: - item, * item, + item -> • item
    # (must be done before italic to avoid * conflicts)
    text = re.sub(r'^([ \t]*)[-*+]\s+', r'\1• ', text, flags=re.MULTILINE)
    # Ordered: 1. item -> 1. item (normalize spacing only)
    text = re.sub(r'^([ \t]*)(\d+)\.\s+', r'\1\2. ', text, flags=re.MULTILINE)

    # Now escape HTML in the remaining text
    text = html.escape(text)

    # Convert Markdown to HTML
    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic: *text* or _text_ (but not inside words for _)
    text = re.sub(r'(?<!\w)\*([^*]+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', text)

    # Strikethrough: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

    # Links: [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Restore code blocks
    for i, code in enumerate(code_blocks):
        escaped_code = html.escape(code)
        text = text.replace(f"\x00CODEBLOCK{i}\x00", f"<pre>{escaped_code}</pre>")

    # Restore inline code
    for i, code in enumerate(inline_codes):
        escaped_code = html.escape(code)
        text = text.replace(f"\x00INLINECODE{i}\x00", f"<code>{escaped_code}</code>")

    return text


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks that fit within Telegram's limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    # Split by paragraphs first
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_length:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            # If current chunk is not empty, save it
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # If paragraph itself is too long, split by lines
            if len(para) > max_length:
                lines = para.split("\n")
                for line in lines:
                    if len(current_chunk) + len(line) + 1 <= max_length:
                        if current_chunk:
                            current_chunk += "\n" + line
                        else:
                            current_chunk = line
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        # If line itself is too long, force split
                        if len(line) > max_length:
                            for i in range(0, len(line), max_length):
                                chunks.append(line[i : i + max_length])
                            current_chunk = ""
                        else:
                            current_chunk = line
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
