"""Discord attachment/text payload builder."""

from __future__ import annotations

import base64

import discord

from utils import decode_file_content, get_file_extension, is_image_file, is_likely_text, is_text_file
from utils.platform_parity import build_analyze_uploaded_files_message

from ..config import MAX_FILE_SIZE, MAX_TEXT_CONTENT_LENGTH, MIME_TYPE_MAP


def _attachment_to_parts(attachment: discord.Attachment, file_bytes: bytes, *, text_blocks: list[str], image_parts: list[dict], unsupported_files: list[str]) -> None:
    file_name = attachment.filename or "unknown"
    if (attachment.content_type or "").startswith("image/") or is_image_file(file_name):
        image_base64 = base64.b64encode(file_bytes).decode("utf-8")
        content_type = attachment.content_type or ""
        if content_type.startswith("image/"):
            mime = content_type.split(";", 1)[0].split("/", 1)[1]
        else:
            ext = get_file_extension(file_name).replace(".", "")
            mime = MIME_TYPE_MAP.get(ext, "jpeg")
        image_parts.append({"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{image_base64}"}})
        return
    if is_text_file(file_name) or is_likely_text(file_bytes):
        file_content = decode_file_content(file_bytes)
        if file_content is None:
            unsupported_files.append(file_name)
            return
        truncated = len(file_content) > MAX_TEXT_CONTENT_LENGTH
        if truncated:
            file_content = file_content[:MAX_TEXT_CONTENT_LENGTH]
        label = f"[File: {file_name}]"
        if truncated:
            label += " (truncated)"
        text_blocks.append(f"{label}\n\n```\n{file_content}\n```")
        return
    unsupported_files.append(file_name)


async def build_user_content_from_message(message: discord.Message, user_text: str) -> tuple[str | list[dict], str]:
    attachments = message.attachments or []
    if not attachments:
        save_msg = user_text.strip() if user_text.strip() else "[Empty message]"
        return user_text.strip(), save_msg
    oversized: list[str] = []
    text_blocks: list[str] = []
    image_parts: list[dict] = []
    unsupported_files: list[str] = []
    file_names: list[str] = []
    for attachment in attachments:
        file_name = attachment.filename or "unknown"
        file_names.append(file_name)
        if attachment.size and attachment.size > MAX_FILE_SIZE:
            oversized.append(file_name)
            continue
        try:
            file_bytes = await attachment.read()
        except Exception:
            unsupported_files.append(file_name)
            continue
        _attachment_to_parts(attachment, file_bytes, text_blocks=text_blocks, image_parts=image_parts, unsupported_files=unsupported_files)
    text_sections: list[str] = []
    if user_text.strip():
        text_sections.append(user_text.strip())
    if text_blocks:
        text_sections.append("\n\n".join(text_blocks))
    if oversized:
        blocked = ", ".join(oversized[:5]) + (", ..." if len(oversized) > 5 else "")
        text_sections.append(f"Skipped oversized files (max 20MB): {blocked}")
    if unsupported_files:
        skipped = ", ".join(unsupported_files[:5]) + (", ..." if len(unsupported_files) > 5 else "")
        text_sections.append(f"Skipped unsupported files: {skipped}")
    text_prompt = "\n\n".join(text_sections).strip()
    if image_parts:
        user_content: str | list[dict] = list(image_parts)
        if text_prompt:
            user_content.insert(0, {"type": "text", "text": text_prompt})
    else:
        user_content = text_prompt or build_analyze_uploaded_files_message()
    if len(file_names) == 1:
        save_msg = f"[File: {file_names[0]}]"
    else:
        preview = ", ".join(file_names[:3]) + (", ..." if len(file_names) > 3 else "")
        save_msg = f"[Files x{len(file_names)}] {preview}"
    if user_text.strip():
        save_msg = f"{save_msg} {user_text.strip()}"
    return user_content, save_msg
