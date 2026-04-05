"""Telegram command context adapter for shared command core."""

from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes


class TelegramCommandContextAdapter:
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context
        self.local_user_id = int(update.effective_user.id)
        self.local_chat_id = int(update.effective_chat.id)
        self.is_group = update.effective_chat.type in ("group", "supergroup")
        self.export_dir = "runtime/telegram/exports"

    async def reply_text(self, text: str) -> None:
        await self.update.message.reply_text(text)

    async def reply_file(self, file_path: str | Path, *, caption: str = "") -> None:
        path = Path(file_path)
        await self.update.message.reply_document(
            document=str(path),
            filename=path.name,
            caption=caption,
        )

    async def reply_document_buffer(self, file_buffer, *, filename: str | None = None, caption: str = "") -> None:
        name = filename or getattr(file_buffer, "name", None)
        await self.update.message.reply_document(
            document=file_buffer,
            filename=name,
            caption=caption,
        )

    async def send_private_text(self, text: str) -> None:
        await self.context.bot.send_message(
            chat_id=self.local_user_id,
            text=text,
            disable_web_page_preview=True,
        )
