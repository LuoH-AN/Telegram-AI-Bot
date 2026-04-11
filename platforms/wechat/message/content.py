"""Build model input payload from WeChat inbound message.

Handles both old dict-based messages and new wechatbot-sdk IncomingMessage objects.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from config import MAX_FILE_SIZE, MAX_TEXT_CONTENT_LENGTH
from utils import decode_file_content, is_image_file, is_likely_text, is_text_file
from utils.platform_parity import build_analyze_uploaded_files_message

from ..config import WECHAT_STATE_DIR, logger
from .extract import extract_text_body


async def build_user_content_from_wechat_message(runtime, message, *, is_group: bool = False) -> tuple[str | list[dict], str]:
    """Build user content from an inbound message.

    ``message`` can be either:
    - a dict (legacy format)
    - an IncomingMessage from wechatbot-sdk
    """
    # Detect SDK IncomingMessage vs legacy dict
    is_sdk_msg = hasattr(message, "user_id") and hasattr(message, "raw")
    if is_sdk_msg:
        return await _build_from_sdk_message(runtime, message)
    return await _build_from_legacy_message(runtime, message, is_group=is_group)


async def _build_from_sdk_message(runtime, msg) -> tuple[str | list[dict], str]:
    """Build content from a wechatbot-sdk IncomingMessage."""
    text_blocks: list[str] = []
    image_parts: list[dict] = []
    unsupported_files: list[str] = []
    file_names: list[str] = []

    primary_text = str(getattr(msg, "text", "") or "").strip()

    # Process quoted/referenced message
    quoted = getattr(msg, "quoted_message", None)
    if quoted:
        quoted_parts: list[str] = []
        if getattr(quoted, "title", None):
            quoted_parts.append(str(quoted.title))
        if getattr(quoted, "text", None):
            quoted_parts.append(str(quoted.text))
        if quoted_parts:
            quoted_str = f"[Quoted: {' | '.join(quoted_parts)}]"
            if primary_text:
                primary_text = f"{quoted_str}\n{primary_text}"
            else:
                primary_text = quoted_str

    images = getattr(msg, "images", None) or []
    files = getattr(msg, "files", None) or []
    videos = getattr(msg, "videos", None) or []
    voices = getattr(msg, "voices", None) or []
    for v in voices:
        voice_text = str(getattr(v, "text", "") or "").strip()
        if voice_text:
            text_blocks.append(voice_text)
        else:
            unsupported_files.append("voice (no transcription)")

    if images or files or videos:
        try:
            downloaded = await runtime.client.download_media(msg)
        except Exception:
            logger.debug("Failed to download WeChat attachment", exc_info=True)
            downloaded = None

        if downloaded and getattr(downloaded, "data", None):
            _append_downloaded_bytes(
                data=downloaded.data,
                file_name=_sdk_download_file_name(msg, downloaded, file_names=file_names),
                media_type=getattr(downloaded, "type", "file"),
                text_blocks=text_blocks,
                image_parts=image_parts,
                unsupported_files=unsupported_files,
                file_names=file_names,
            )
        elif images:
            unsupported_files.append("image")
        elif files:
            unsupported_files.append(str(getattr(files[0], "file_name", None) or "file"))
        elif videos:
            unsupported_files.append("video")

    extra_media = max(len(images), len(files), len(videos)) - 1
    if extra_media > 0:
        unsupported_files.append(f"additional attachments x{extra_media}")

    if primary_text:
        text_blocks.insert(0, primary_text)
    text_prompt = "\n\n".join(part for part in text_blocks if part).strip()
    if unsupported_files:
        suffix = ", ".join(unsupported_files[:5]) + (", ..." if len(unsupported_files) > 5 else "")
        text_prompt += ("\n\n" if text_prompt else "") + "Skipped unsupported files: " + suffix

    if image_parts:
        user_content: str | list[dict] = list(image_parts)
        if text_prompt:
            user_content.insert(0, {"type": "text", "text": text_prompt})
    else:
        user_content = text_prompt or build_analyze_uploaded_files_message()
    save_msg = _build_save_message(file_names, text_prompt)
    return user_content, save_msg


async def _build_from_legacy_message(runtime, message: dict, *, is_group: bool = False) -> tuple[str | list[dict], str]:
    """Legacy dict-based message builder (kept for backward compat)."""
    from .content_files import append_downloaded_file
    from .extract import strip_wechat_group_mentions

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
            if not hasattr(runtime.client, "download_media_to_path"):
                raise AttributeError("Legacy download_media_to_path not available with SDK adapter")
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
    from .content_files import build_save_message
    return user_content, build_save_message(file_names, text_prompt)


def _append_downloaded_bytes(
    *,
    data: bytes,
    file_name: str,
    media_type: str,
    text_blocks: list[str],
    image_parts: list[dict],
    unsupported_files: list[str],
    file_names: list[str],
) -> None:
    file_names.append(file_name)
    if len(data) > MAX_FILE_SIZE:
        unsupported_files.append(f"{file_name} (oversized)")
        return
    if media_type == "image" or is_image_file(file_name):
        image_b64 = base64.b64encode(data).decode("utf-8")
        mime = "image/jpeg"
        if file_name.lower().endswith(".png"):
            mime = "image/png"
        elif file_name.lower().endswith(".gif"):
            mime = "image/gif"
        elif file_name.lower().endswith(".webp"):
            mime = "image/webp"
        image_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}})
        return
    if is_text_file(file_name) or is_likely_text(data):
        file_content = decode_file_content(data)
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


def _sdk_download_file_name(msg, downloaded, *, file_names: list[str]) -> str:
    file_name = str(getattr(downloaded, "file_name", None) or "").strip()
    if file_name:
        return file_name
    media_type = str(getattr(downloaded, "type", "file") or "file").strip().lower()
    if media_type == "image":
        return f"image_{len(file_names) + 1}.jpg"
    if media_type == "video":
        return f"video_{len(file_names) + 1}.mp4"
    if media_type == "voice":
        fmt = str(getattr(downloaded, "format", None) or "silk").strip().lower()
        return f"voice_{len(file_names) + 1}.{fmt}"
    msg_files = getattr(msg, "files", None) or []
    if msg_files:
        candidate = str(getattr(msg_files[0], "file_name", None) or "").strip()
        if candidate:
            return candidate
    return f"file_{len(file_names) + 1}.bin"


def _build_save_message(file_names: list[str], text_prompt: str) -> str:
    if len(file_names) == 1:
        return f"[File: {file_names[0]}]"
    if file_names:
        preview = ", ".join(file_names[:3]) + (", ..." if len(file_names) > 3 else "")
        return f"[Files x{len(file_names)}] {preview}"
    return text_prompt or "[Message]"
