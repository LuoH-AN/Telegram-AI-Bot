"""Handle .txt file uploads sent with a /persona prompt or /set global_prompt caption."""

from __future__ import annotations

import base64
from pathlib import Path

import aiohttp

from config import MAX_FILE_SIZE
from platforms.shared import apply_prompt_upload, parse_prompt_upload_caption
from utils.files import decode_file_content, is_likely_text, is_text_file


async def _bytes_from_url(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                return data if len(data) <= MAX_FILE_SIZE else None
    except Exception:
        return None


def _read_local(path_str: str) -> bytes | None:
    try:
        path = Path(path_str)
        if not path.exists() or path.stat().st_size > MAX_FILE_SIZE:
            return None
        return path.read_bytes()
    except Exception:
        return None


async def _resolve_file_bytes(client, seg: dict) -> tuple[bytes | None, str]:
    name = str(seg.get("name") or seg.get("file_name") or seg.get("file") or "").strip() or "file.txt"
    file_id = seg.get("file_id") or seg.get("file")
    if file_id:
        try:
            info = await client.get_file(str(file_id))
        except Exception:
            info = None
        if isinstance(info, dict):
            if info.get("base64"):
                try:
                    return base64.b64decode(info["base64"]), str(info.get("file_name") or name)
                except Exception:
                    pass
            if info.get("file") and (data := _read_local(str(info["file"]))) is not None:
                return data, str(info.get("file_name") or name)
            if info.get("url") and (data := await _bytes_from_url(str(info["url"]))) is not None:
                return data, str(info.get("file_name") or name)
    if seg.get("url") and (data := await _bytes_from_url(str(seg["url"]))) is not None:
        return data, name
    return None, name


async def _extract_first_text_file(client, files: list[dict]) -> str | None:
    for seg in files:
        data, name = await _resolve_file_bytes(client, seg)
        if data is None:
            continue
        if not (is_text_file(name) or is_likely_text(bytearray(data))):
            continue
        decoded = decode_file_content(bytearray(data))
        if decoded is not None:
            return decoded
    return None


async def _extract_pending_group_text(client, group_id: int, pending) -> str | None:
    try:
        info = await client.get_group_file_url(group_id, pending.file_id, busid=pending.busid)
    except Exception:
        return None
    if not isinstance(info, dict) or not info.get("url"):
        return None
    data = await _bytes_from_url(str(info["url"]))
    if data is None:
        return None
    name = pending.file_name or str(info.get("file_name") or "")
    if not (is_text_file(name) or is_likely_text(bytearray(data))):
        return None
    return decode_file_content(bytearray(data))


async def try_handle_prompt_upload(runtime, ctx, inbound) -> bool:
    command = parse_prompt_upload_caption(inbound.normalized_text)
    if command is None:
        return False
    text: str | None = None
    if inbound.files:
        text = await _extract_first_text_file(runtime.client, list(inbound.files))
    elif inbound.is_group and inbound.group_id:
        from .pending_uploads import consume_upload

        pending = consume_upload(int(inbound.group_id), int(inbound.user_id))
        if pending is None:
            await ctx.reply_text(
                "Upload a .txt file to this group first, then re-run this "
                "command within 5 minutes."
            )
            return True
        text = await _extract_pending_group_text(
            runtime.client, int(inbound.group_id), pending,
        )
    else:
        return False
    if text is None:
        await ctx.reply_text(
            "No readable .txt file found. Attach a UTF-8 text file with this command."
        )
        return True
    reply = apply_prompt_upload(command, ctx.session_user_id, text)
    await ctx.reply_text(reply)
    return True

