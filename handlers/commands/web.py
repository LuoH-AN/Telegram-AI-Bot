"""Handler for the /web command — sends a dashboard link with JWT token."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import WEB_BASE_URL
from web.auth import create_short_token
from handlers.common import get_log_context
from utils.platform_parity import (
    build_web_dashboard_message,
    build_web_dm_failed_message,
    build_web_dm_sent_message,
)

logger = logging.getLogger(__name__)


async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a short token link and send it privately."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    ctx = get_log_context(update)
    logger.info("%s /web", ctx)

    token = create_short_token(user_id)
    # Include both query + hash token to handle clients that strip URL fragments.
    url = f"{WEB_BASE_URL.rstrip('/')}/?token={token}#token={token}"
    text = build_web_dashboard_message(url)

    if chat_type in ("group", "supergroup"):
        # Send via private message to avoid leaking the token in group chat
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                disable_web_page_preview=True,
            )
            await update.message.reply_text(build_web_dm_sent_message())
        except Exception:
            await update.message.reply_text(build_web_dm_failed_message())
    else:
        await update.message.reply_text(text, disable_web_page_preview=True)
