"""Telegram OutboundSender — wraps Update/Context for media replies."""

from __future__ import annotations

import io

from telegram import Update
from telegram.ext import ContextTypes

from adapters.telegram.outbound import OutboundSender


def _buf(data: bytes, filename: str) -> io.BytesIO:
    buf = io.BytesIO(data)
    buf.name = filename
    return buf


class TelegramOutbound(OutboundSender):
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context

    async def send_image(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.update.message.reply_photo(photo=_buf(data, filename), caption=caption or None)

    async def send_document(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.update.message.reply_document(
            document=_buf(data, filename), filename=filename, caption=caption or None
        )

    async def send_voice(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.update.message.reply_voice(voice=_buf(data, filename), caption=caption or None)

    async def send_video(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.update.message.reply_video(video=_buf(data, filename), caption=caption or None)
