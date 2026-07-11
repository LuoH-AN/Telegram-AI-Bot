"""send_file tool — push media (image/document/voice/video) into the active chat.

Uses ctx.outbound (injected) instead of importing the adapter layer directly —
fixes the infrastructure→adapter dependency inversion of the old plugin.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from . import sources

logger = logging.getLogger(__name__)

SEND_FILE_INSTRUCTION = (
    "\nsend_file usage:\n"
    "- `send_file` sends an existing public URL to the active chat.\n"
    "- `send_local_file` is admin-only and sends an allowed local path.\n"
    "- This tool sends existing media only and cannot generate images or other content.\n"
    "- Max 50MB. Caption is optional and should be short.\n"
)

_SENDERS = {"image": "send_image", "voice": "send_voice", "video": "send_video", "document": "send_document"}


def _safe_filename(value: str, fallback: str) -> str:
    name = (value or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if ord(char) >= 32 and char not in {"\x7f"})
    return (name[:180].strip() or fallback)[:180]


async def _deliver(ctx: ToolContext, kind: str, data: bytes, default_name: str, filename: str, caption: str) -> ToolResult:
    binding = ctx.outbound
    if binding is None:
        return ToolResult.error("no_active_chat", "file delivery requires an active user chat")
    name = _safe_filename(filename, default_name)
    send = getattr(binding.sender, _SENDERS[kind])
    try:
        await send(data, filename=name, caption=(caption or "").strip()[:1024])
    except Exception as exc:
        logger.exception("file delivery failed")
        return ToolResult.error("send_failed", f"send failed: {exc}")
    return ToolResult.text(f"Sent {kind} ({len(data)} bytes) as '{name}'")


@tool(toolset="user", skill="send_file", side_effects=True, instruction=SEND_FILE_INSTRUCTION, description="Download an existing public URL and send it as an image, document, voice, or video to the active chat.")
async def send_file(
    ctx: ToolContext,
    kind: Literal["image", "document", "voice", "video"],
    url: Annotated[str, "Public HTTP(S) URL of the existing file."],
    filename: Annotated[str, "Display filename (optional)."] = "",
    caption: Annotated[str, "Optional caption."] = "",
) -> ToolResult:
    url = (url or "").strip()
    if not url:
        return ToolResult.error("missing_url", "url is required")
    try:
        data, default_name = await asyncio.to_thread(sources.fetch_url, url, kind=kind)
    except Exception as exc:
        logger.warning("send_file resolve failed: %s", exc)
        return ToolResult.error("resolve_failed", f"could not load source: {exc}")
    return await _deliver(ctx, kind, data, default_name, filename, caption)


@tool(toolset="admin", skill="send_file", danger=True, side_effects=True, instruction=SEND_FILE_INSTRUCTION, description="Admin-only: send an existing local file from an allowed root to the active chat.")
async def send_local_file(
    ctx: ToolContext,
    kind: Literal["image", "document", "voice", "video"],
    path: Annotated[str, "Existing local file path inside an allowed root."],
    filename: Annotated[str, "Display filename (optional)."] = "",
    caption: Annotated[str, "Optional caption."] = "",
) -> ToolResult:
    path = (path or "").strip()
    if not path:
        return ToolResult.error("missing_path", "path is required")
    try:
        data, default_name = await asyncio.to_thread(sources.read_path, path, kind=kind)
    except Exception as exc:
        logger.warning("send_local_file resolve failed: %s", exc)
        return ToolResult.error("resolve_failed", f"could not load source: {exc}")
    return await _deliver(ctx, kind, data, default_name, filename, caption)
