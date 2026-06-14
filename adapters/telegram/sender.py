"""Telegram OutboundSender — wraps Update/Context for media replies."""

from __future__ import annotations

import io

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from adapters.telegram.outbound import OutboundSender
from shared.utils.format import markdown_to_telegram_html


def _buf(data: bytes, filename: str) -> io.BytesIO:
    buf = io.BytesIO(data)
    buf.name = filename
    return buf


def _caption(text: str) -> str | None:
    return markdown_to_telegram_html(text) or None


class TelegramOutbound(OutboundSender):
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context
        self.message = update.effective_message

    async def send_image(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_photo(
            photo=_buf(data, filename),
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )

    async def send_document(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_document(
            document=_buf(data, filename),
            filename=filename,
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )

    async def send_voice(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_voice(
            voice=_buf(data, filename),
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )

    async def send_video(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_video(
            video=_buf(data, filename),
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )
