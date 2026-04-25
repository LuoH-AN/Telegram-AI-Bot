"""Attachment processing helpers for inbound WeChat messages."""

from __future__ import annotations

import base64
from pathlib import Path

from config import MAX_FILE_SIZE, MAX_TEXT_CONTENT_LENGTH
from utils.files import decode_file_content, is_image_file, is_likely_text, is_text_file


def append_downloaded_file(
    *,
    item_type: int,
    downloaded: dict,
    text_blocks: list[str],
    image_parts: list[dict],
    unsupported_files: list[str],
    oversized_files: list[str],
    file_names: list[str],
) -> None:
    file_path = Path(str(downloaded["path"]))
    file_name = str(downloaded.get("filename") or file_path.name)
    file_names.append(file_name)
    if file_path.stat().st_size > MAX_FILE_SIZE:
        oversized_files.append(file_name)
        return
    file_bytes = file_path.read_bytes()
    if item_type == 2 or is_image_file(file_name):
        image_b64 = base64.b64encode(file_bytes).decode("utf-8")
        mime = str(downloaded.get("media_type") or "image/jpeg")
        image_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}})
        return
    if is_text_file(file_name) or is_likely_text(file_bytes):
        file_content = decode_file_content(file_bytes)
        if file_content is None:
            unsupported_files.append(file_name)
            return
        truncated = len(file_content) > MAX_TEXT_CONTENT_LENGTH
        if truncated:
            file_content = file_content[:MAX_TEXT_CONTENT_LENGTH]
        label = f"[File: {file_name}]" + (" (truncated)" if truncated else "")
        text_blocks.append(f"{label}\n\n```\n{file_content}\n```")
        return
    unsupported_files.append(file_name)


def build_save_message(file_names: list[str], text_prompt: str) -> str:
    if len(file_names) == 1:
        return f"[File: {file_names[0]}]"
    if file_names:
        preview = ", ".join(file_names[:3]) + (", ..." if len(file_names) > 3 else "")
        return f"[Files x{len(file_names)}] {preview}"
    return text_prompt or "[Message]"
