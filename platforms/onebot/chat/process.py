"""Inbound chat processing for OneBot/QQ messages."""

from __future__ import annotations

import asyncio
import time

from platforms.shared.chat import process_inbound_chat
from platforms.onebot.outbound import OneBotOutbound


async def process_chat_message(runtime, ctx, inbound) -> None:
    """Process an inbound OneBot message."""
    user_content = inbound.text_body
    save_msg = user_content
    record_bot_reply = None

    if ctx.is_group:
        from ..proactive import build_chatroom_user_content, extract_nickname, record_bot

        gid = int(inbound.group_id)
        record_bot_reply = lambda text: record_bot(gid, text)

        if not getattr(ctx, "proactive_direct", True):
            user_content = build_chatroom_user_content(
                group_id=gid,
                nickname=extract_nickname(inbound.raw_event),
                new_text=inbound.text_body,
            )

    slot_key = (
        f"onebot:{ctx.local_chat_id}:{ctx.local_user_id}:"
        f"{inbound.message_id or int(time.time() * 1000)}"
    )

    async def _send_tool_status(text: str) -> None:
        await runtime.send_text_to_peer(
            ctx.reply_to_id,
            text,
            is_group=ctx.is_group,
            dedupe_key=None,
        )

    await process_inbound_chat(
        ctx=ctx,
        platform="onebot",
        user_content=user_content,
        save_msg=save_msg,
        slot_key=slot_key,
        session_user_id=ctx.session_user_id,
        send_tool_status=_send_tool_status,
        typing_factory=None,
        outbound_factory=lambda: OneBotOutbound(ctx),
        on_assistant_reply=record_bot_reply,
    )
