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
    "- Use for sending images/files to the user. Text answers still go in the regular reply.\n"
    "- source='url' downloads first; 'path' reads a local file; 'generate' creates an image from prompt.\n"
    "- Max 50MB. Caption is optional and should be short.\n"
)

_SENDERS = {"image": "send_image", "voice": "send_voice", "video": "send_video", "document": "send_document"}


@tool(toolset="user", skill="send_file", instruction=SEND_FILE_INSTRUCTION, description="Send a media message (image, document, voice, video) directly into the current chat. Only works during an active reply. source: url/path/generate (generate = image only).")
async def send_file(
    ctx: ToolContext,
    kind: Literal["image", "document", "voice", "video"],
    source: Literal["url", "path", "generate"],
    url: Annotated[str, "URL when source=url."] = "",
    path: Annotated[str, "Local file path when source=path."] = "",
    prompt: Annotated[str, "Image generation prompt when source=generate."] = "",
    filename: Annotated[str, "Display filename (optional)."] = "",
    caption: Annotated[str, "Optional caption."] = "",
    size: Annotated[str, "Image size when source=generate, e.g. 1024x1024."] = "1024x1024",
) -> ToolResult:
    if source == "generate" and kind != "image":
        return ToolResult.error("invalid_combo", "source='generate' only supported for kind='image'")
    binding = ctx.outbound
    if binding is None:
        return ToolResult.error("no_active_chat", "send_file can only be used while replying to the user")

    try:
        if source == "url":
            url = (url or "").strip()
            if not url:
                return ToolResult.error("missing_url", "url required when source=url")
            data, default_name = await asyncio.to_thread(sources.fetch_url, url, kind=kind)
        elif source == "path":
            path = (path or "").strip()
            if not path:
                return ToolResult.error("missing_path", "path required when source=path")
            data, default_name = await asyncio.to_thread(sources.read_path, path, kind=kind)
        else:
            prompt = (prompt or "").strip()
            if not prompt:
                return ToolResult.error("missing_prompt", "prompt required when source=generate")
            data, default_name = await asyncio.to_thread(sources.generate_image, ctx.user_id, prompt, size=(size or "1024x1024"))
    except Exception as exc:
        logger.warning("send_file resolve failed: %s", exc)
        return ToolResult.error("resolve_failed", f"could not load source: {exc}")

    name = (filename or "").strip() or default_name
    send = getattr(binding.sender, _SENDERS[kind])
    try:
        await send(data, filename=name, caption=(caption or "").strip())
    except Exception as exc:
        logger.exception("send_file delivery failed")
        return ToolResult.error("send_failed", f"send failed: {exc}")
    return ToolResult.text(f"Sent {kind} ({len(data)} bytes) as '{name}'")
