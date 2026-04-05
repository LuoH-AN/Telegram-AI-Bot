"""Build model input payload from WeChat inbound message."""

from __future__ import annotations

import asyncio
from pathlib import Path

from utils.platform_parity import build_analyze_uploaded_files_message

from ..config import WECHAT_STATE_DIR, logger
from .content_files import append_downloaded_file, build_save_message
from .extract import extract_text_body, strip_wechat_group_mentions


async def build_user_content_from_wechat_message(runtime, message: dict, *, is_group: bool = False) -> tuple[str | list[dict], str]:
    item_list = list(message.get("item_list") or [])
    primary_text = extract_text_body(item_list)
    if is_group:
        primary_text = strip_wechat_group_mentions(primary_text)
    text_blocks: list[str] = []
    image_parts: list[dict] = []
    unsupported_files: list[str] = []
    oversized_files: list[str] = []
    file_names: list[str] = []

    for item in item_list:
        item_type = int(item.get("type") or 0)
        if item_type in {1}:
            continue
        if item_type == 3:
            if not str((item.get("voice_item") or {}).get("text") or "").strip():
                unsupported_files.append("voice")
            continue
        if item_type not in {2, 4, 5}:
            continue
        try:
            downloaded = await asyncio.to_thread(runtime.client.download_media_to_path, item, Path(WECHAT_STATE_DIR) / "inbound")
        except Exception:
            logger.debug("Failed to download WeChat attachment", exc_info=True)
            unsupported_files.append(f"attachment(type={item_type})")
            continue
        append_downloaded_file(
            item_type=item_type,
            downloaded=downloaded,
            text_blocks=text_blocks,
            image_parts=image_parts,
            unsupported_files=unsupported_files,
            oversized_files=oversized_files,
            file_names=file_names,
        )

    if primary_text:
        text_blocks.insert(0, primary_text)
    text_prompt = "\n\n".join(part for part in text_blocks if part).strip()
    if oversized_files:
        suffix = ", ".join(oversized_files[:5]) + (", ..." if len(oversized_files) > 5 else "")
        text_prompt += ("\n\n" if text_prompt else "") + "Skipped oversized files (max 20MB): " + suffix
    if unsupported_files:
        suffix = ", ".join(unsupported_files[:5]) + (", ..." if len(unsupported_files) > 5 else "")
        text_prompt += ("\n\n" if text_prompt else "") + "Skipped unsupported files: " + suffix

    if image_parts:
        user_content: str | list[dict] = list(image_parts)
        if text_prompt:
            user_content.insert(0, {"type": "text", "text": text_prompt})
    else:
        user_content = text_prompt or build_analyze_uploaded_files_message()
    return user_content, build_save_message(file_names, text_prompt)
