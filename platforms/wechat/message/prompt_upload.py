"""Extract the first readable text file from a WeChat inbound message."""

from __future__ import annotations

from config import MAX_FILE_SIZE
from platforms.shared import apply_prompt_upload, parse_prompt_upload_caption
from utils.files import decode_file_content, is_image_file, is_likely_text, is_text_file


async def extract_first_text_file_sdk(runtime, msg) -> str | None:
    files = getattr(msg, "files", None) or []
    images = getattr(msg, "images", None) or []
    videos = getattr(msg, "videos", None) or []
    if not (files or images or videos):
        return None
    try:
        downloaded = await runtime.client.download_media(msg)
    except Exception:
        return None
    data = getattr(downloaded, "data", None) if downloaded else None
    if not data:
        return None
    if len(data) > MAX_FILE_SIZE:
        return None
    file_name = str(getattr(downloaded, "file_name", "") or "").strip()
    media_type = str(getattr(downloaded, "type", "") or "").strip().lower()
    if media_type == "image" or (file_name and is_image_file(file_name)):
        return None
    if file_name and not is_text_file(file_name) and not is_likely_text(data):
        return None
    if not file_name and not is_likely_text(data):
        return None
    return decode_file_content(data)


async def try_handle_prompt_upload_sdk(runtime, ctx, msg, caption: str) -> bool:
    command = parse_prompt_upload_caption(caption)
    if command is None:
        return False
    text = await extract_first_text_file_sdk(runtime, msg)
    if text is None:
        await runtime.send_text_to_peer(
            ctx.reply_to_id,
            "No readable .txt file found. Send a UTF-8 text file with this command as caption.",
            context_token=ctx.context_token,
            dedupe_key=None,
        )
        return True
    reply = apply_prompt_upload(command, ctx.local_user_id, text)
    await runtime.send_text_to_peer(
        ctx.reply_to_id, reply, context_token=ctx.context_token, dedupe_key=None,
    )
    return True

