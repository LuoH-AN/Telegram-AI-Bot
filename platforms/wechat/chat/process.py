"""Inbound chat processing for WeChat messages."""

from __future__ import annotations

import asyncio
import time

from platforms.shared.chat import process_inbound_chat

from ..message.content import build_user_content_from_wechat_message


async def process_chat_message(runtime, ctx, message) -> None:
    """Process an inbound WeChat message."""
    user_content, save_msg = await build_user_content_from_wechat_message(
        runtime, message, is_group=False
    )

    raw_message_id = ""
    if isinstance(message, dict):
        raw_message_id = str(message.get("message_id") or "")
    else:
        raw_message_id = str(getattr(message, "raw", {}).get("message_id") or "")
    fallback = ctx.inbound_key or raw_message_id or int(time.time() * 1000)
    slot_key = f"wechat:{ctx.local_chat_id}:{ctx.local_user_id}:{fallback}"

    async def _send_tool_status(text: str) -> None:
        await runtime.send_text_to_peer(
            ctx.reply_to_id,
            text,
            context_token=ctx.context_token,
            dedupe_key=None,
        )

    def _typing_factory():
        stop = asyncio.Event()
        task = asyncio.create_task(
            runtime._typing_loop(ctx.reply_to_id, ctx.context_token, stop)
        )
        return stop, task

    await process_inbound_chat(
        ctx=ctx,
        platform="wechat",
        user_content=user_content,
        save_msg=save_msg,
        slot_key=slot_key,
        send_tool_status=_send_tool_status,
        typing_factory=_typing_factory,
    )
