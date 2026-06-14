"""Telegram command context adapter for shared command application.use_cases."""

from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from shared.utils.format import markdown_to_telegram_html


class TelegramCommandContextAdapter:
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context
        self.message = update.effective_message
        self.local_user_id = int(update.effective_user.id)
        self.local_chat_id = int(update.effective_chat.id)
        self.session_user_id = self.local_user_id
        self.is_group = update.effective_chat.type in ("group", "supergroup")
        self.export_dir = "runtime/telegram/exports"

    async def reply_text(self, text: str) -> None:
        html_text = markdown_to_telegram_html(text)
        await self.message.reply_text(html_text, parse_mode=ParseMode.HTML)

    async def reply_file(self, file_path: str | Path, *, caption: str = "") -> None:
        path = Path(file_path)
        await self.message.reply_document(
            document=str(path),
            filename=path.name,
            caption=markdown_to_telegram_html(caption) or None,
            parse_mode=ParseMode.HTML,
        )

    async def reply_document_buffer(self, file_buffer, *, filename: str | None = None, caption: str = "") -> None:
        name = filename or getattr(file_buffer, "name", None)
        await self.message.reply_document(
            document=file_buffer,
            filename=name,
            caption=markdown_to_telegram_html(caption) or None,
            parse_mode=ParseMode.HTML,
        )

    async def reply_photo_url(self, url: str, *, caption: str = "") -> None:
        await self.message.reply_photo(
            photo=url,
            caption=markdown_to_telegram_html(caption) or None,
            parse_mode=ParseMode.HTML,
        )

    async def send_private_text(self, text: str) -> None:
        html_text = markdown_to_telegram_html(text)
        await self.context.bot.send_message(
            chat_id=self.local_user_id,
            text=html_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    async def send_private_photo_url(self, url: str, *, caption: str = "") -> None:
        await self.context.bot.send_photo(
            chat_id=self.local_user_id,
            photo=url,
            caption=markdown_to_telegram_html(caption) or None,
            parse_mode=ParseMode.HTML,
        )
