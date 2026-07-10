"""Telegram global error handler."""

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes


def build_error_handler(logger: logging.Logger):
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        error = context.error
        if isinstance(error, TelegramError) and "Invalid server response" in str(error):
            logger.warning("Telegram API returned invalid response (likely proxy issue), will retry automatically")
            return

        user_id = update.effective_user.id if isinstance(update, Update) and update.effective_user else None
        suffix = f" [user={user_id}]" if user_id else ""
        logger.error("Unhandled exception%s: %s", suffix, error, exc_info=context.error)

        if not user_id:
            return
        try:
            from domain.services.log import record_error

            record_error(user_id, str(error), "global error handler")
        except Exception:
            logger.debug("Failed to persist global error", exc_info=True)
        if isinstance(update, Update) and update.effective_message:
            try:
                from adapters.telegram.rich_text import reply_rich_text
                from adapters.telegram.ux.errors import error_panel
                from adapters.telegram.ux.locale import language

                text, keyboard = error_panel(error, language(update, context), user_id=user_id)
                await reply_rich_text(update.effective_message, text, reply_markup=keyboard)
            except Exception:
                logger.debug("Failed to send global error recovery UI", exc_info=True)

    return error_handler
