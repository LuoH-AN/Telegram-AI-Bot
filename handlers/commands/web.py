"""Handler for the /web command — sends a dashboard link with JWT token."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import WEB_BASE_URL
from web.auth import create_short_token

logger = logging.getLogger(__name__)


async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a short token link and send it privately."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    token = create_short_token(user_id)
    url = f"{WEB_BASE_URL}/?token={token}"
    text = f"Open the Gemen dashboard:\n{url}\n\nThis link is single-use and expires in 10 minutes."

    if chat_type in ("group", "supergroup"):
        # Send via private message to avoid leaking the token in group chat
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                disable_web_page_preview=True,
            )
            await update.message.reply_text("Dashboard link sent to your DM.")
        except Exception:
            await update.message.reply_text(
                "Could not send DM. Please start a private chat with me first, then retry."
            )
    else:
        await update.message.reply_text(text, disable_web_page_preview=True)
