"""Render-pump and outbound runtime for Discord streaming."""

from __future__ import annotations

import asyncio

import discord

from utils import ChatEventPump, StreamOutboundAdapter, split_message
from utils.tool_status import build_tool_status_text

from ..config import DISCORD_MAX_MESSAGE_LENGTH, logger
from ..replies import normalize_discord_output_text, safe_edit_message


class ChatRuntime:
    def __init__(self, message: discord.Message, *, log_ctx: str):
        self.message = message
        self.log_ctx = log_ctx
        self.bot_message: discord.Message | None = None
        self.loop = asyncio.get_running_loop()

        async def _edit_placeholder(text: str) -> bool:
            if self.bot_message is None:
                try:
                    self.bot_message = await message.reply(text or "(Empty response)", mention_author=False)
                    return True
                except Exception:
                    logger.exception("%s failed to create discord placeholder", log_ctx)
                    return False
            return await safe_edit_message(self.bot_message, text)

        async def _send_text(text: str) -> bool:
            normalized = normalize_discord_output_text(text or "(Empty response)")
            chunks = split_message(normalized, max_length=DISCORD_MAX_MESSAGE_LENGTH) or ["(Empty response)"]
            try:
                await message.reply(chunks[0], mention_author=False)
                for chunk in chunks[1:]:
                    await message.channel.send(chunk)
                return True
            except Exception:
                logger.exception("%s failed to send discord text chunk", log_ctx)
                return False

        async def _delete_placeholder() -> None:
            if self.bot_message is None:
                return
            try:
                await self.bot_message.delete()
            except Exception:
                pass
            self.bot_message = None

        self.outbound = StreamOutboundAdapter(
            max_message_length=DISCORD_MAX_MESSAGE_LENGTH,
            has_placeholder=lambda: True,
            edit_placeholder=_edit_placeholder,
            send_text=_send_text,
            delete_placeholder=_delete_placeholder,
            empty_placeholder_text="",
        )

        async def _render_event(event) -> None:
            if event.kind in {"stream", "status"}:
                await self.outbound.stream_update(event.text)

        self.render_pump = ChatEventPump(_render_event)
        self.render_pump.start()

    async def stream_update(self, text: str) -> bool:
        return await self.render_pump.emit("stream", text)

    async def status_update(self, text: str) -> bool:
        return await self.render_pump.emit("status", text)

    def tool_event_callback(self, event: dict) -> None:
        status_text = build_tool_status_text(event)
        if status_text:
            self.render_pump.emit_threadsafe(self.loop, "status", status_text)

    def clear_placeholder_reference(self) -> None:
        self.bot_message = None
