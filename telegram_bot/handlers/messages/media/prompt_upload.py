"""Extract the first readable text file from a Telegram document batch."""

from __future__ import annotations

from config import MAX_FILE_SIZE
from utils.files import decode_file_content, is_image_file, is_likely_text, is_text_file


async def extract_first_text_file(grouped_messages, context) -> str | None:
    for message in grouped_messages:
        document = message.document
        if not document:
            continue
        file_name = document.file_name or "unknown"
        if is_image_file(file_name):
            continue
        if document.file_size and document.file_size > MAX_FILE_SIZE:
            continue
        tg_file = await context.bot.get_file(document.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        if not (is_text_file(file_name) or is_likely_text(file_bytes)):
            continue
        decoded = decode_file_content(file_bytes)
        if decoded is None:
            continue
        return decoded
    return None
