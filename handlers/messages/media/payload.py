"""Document payload preparation helpers."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from config import MAX_FILE_SIZE, MAX_TEXT_CONTENT_LENGTH, MIME_TYPE_MAP
from utils import decode_file_content, get_file_extension, is_image_file, is_likely_text, is_text_file
from utils.platform import build_analyze_uploaded_files_message


@dataclass
class DocumentPayload:
    user_content: list[dict] | str
    save_message: str


def _build_skipped_line(title: str, names: list[str]) -> str:
    snippet = ", ".join(names[:5])
    if len(names) > 5:
        snippet += ", ..."
    return f"{title}: {snippet}"


async def build_document_payload(grouped_messages, context, *, caption: str) -> DocumentPayload:
    text_blocks: list[str] = []
    image_parts: list[dict] = []
    unsupported_files: list[str] = []
    oversized_files: list[str] = []
    file_names: list[str] = []

    for message in grouped_messages:
        document = message.document
        if not document:
            continue

        file_name = document.file_name or "unknown"
        file_names.append(file_name)
        file_ext = get_file_extension(file_name)
        if document.file_size and document.file_size > MAX_FILE_SIZE:
            oversized_files.append(file_name)
            continue

        tg_file = await context.bot.get_file(document.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        if is_image_file(file_name):
            image_base64 = base64.b64encode(file_bytes).decode("utf-8")
            ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "jpeg"
            mime_type = MIME_TYPE_MAP.get(ext, "jpeg")
            image_parts.append({"type": "image_url", "image_url": {"url": f"data:image/{mime_type};base64,{image_base64}"}})
            continue

        if is_text_file(file_name) or is_likely_text(file_bytes):
            file_content = decode_file_content(file_bytes)
            if file_content is None:
                unsupported_files.append(file_name)
                continue
            truncated = len(file_content) > MAX_TEXT_CONTENT_LENGTH
            if truncated:
                file_content = file_content[:MAX_TEXT_CONTENT_LENGTH]
            label = f"[File: {file_name}]" + (" (truncated)" if truncated else "")
            text_blocks.append(f"{label}\n\n```\n{file_content}\n```")
            continue

        unsupported_files.append(file_name if file_ext else f"{file_name}(unknown)")

    text_sections = [section for section in (caption, "\n\n".join(text_blocks)) if section]
    if oversized_files:
        text_sections.append(_build_skipped_line("Skipped oversized files (max 20MB)", oversized_files))
    if unsupported_files:
        text_sections.append(_build_skipped_line("Skipped unsupported files", unsupported_files))
    text_prompt = "\n\n".join(text_sections).strip()

    if image_parts:
        user_content = [*image_parts]
        if text_prompt:
            user_content.insert(0, {"type": "text", "text": text_prompt})
    else:
        user_content = text_prompt or build_analyze_uploaded_files_message()

    if len(file_names) == 1:
        save_message = f"[File: {file_names[0]}]"
    else:
        preview = ", ".join(file_names[:3]) + (", ..." if len(file_names) > 3 else "")
        save_message = f"[Files x{len(file_names)}] {preview}"
    if caption:
        save_message += f" {caption}"
    return DocumentPayload(user_content=user_content, save_message=save_message)

