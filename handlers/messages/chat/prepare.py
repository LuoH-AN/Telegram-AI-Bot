from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from handlers.common import get_log_context, should_respond_in_group
from services import (
    ensure_session,
    get_conversation,
    get_current_persona_name,
    get_remaining_tokens,
    get_user_settings,
    has_api_key,
)
from services.refresh import ensure_user_state
from utils.platform_parity import (
    build_api_key_required_message,
    build_retry_message,
    build_token_limit_reached_message,
)

logger = logging.getLogger(__name__)

def _prepare_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE, ctx: str) -> tuple[str, str]:
    user_message = update.message.text
    logger.info("%s text: %s", ctx, user_message[:80])
    bot_username = context.bot.username
    if bot_username and f"@{bot_username}" in user_message:
        user_message = user_message.replace(f"@{bot_username}", "").strip()
    reply_msg = update.message.reply_to_message
    if reply_msg:
        quoted_text = reply_msg.text or reply_msg.caption or ""
        if quoted_text:
            sender = reply_msg.from_user
            sender_name = sender.first_name if sender else "Unknown"
            quoted_preview = quoted_text.strip()
            if len(quoted_preview) > 800:
                quoted_preview = quoted_preview[:800] + "..."
            user_message = (
                f"{user_message}\n\n"
                f"[Reply context from {sender_name}]:\n{quoted_preview}"
            )
    return user_message, user_message

async def _set_typing_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE, ctx: str) -> None:
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction="👁️",
            is_big=False,
        )
    except Exception:
        logger.debug("%s failed to set Telegram reaction", ctx, exc_info=True)

async def prepare_chat_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_content=None,
    save_msg=None,
    frozen_persona_name: str | None = None,
    frozen_session_id: int | None = None,
) -> dict | None:
    internal_call = user_content is not None
    if not internal_call and (not await should_respond_in_group(update, context) or update.message.forward_origin):
        return None
    user_id = update.effective_user.id
    ctx = get_log_context(update)
    ensure_user_state(user_id)
    if not internal_call:
        user_content, save_msg = _prepare_user_text(update, context, ctx)
    else:
        logger.info("%s media: %s", ctx, (save_msg or "")[:80])

    settings = get_user_settings(user_id)
    if not internal_call and not has_api_key(user_id):
        await update.message.reply_text(build_api_key_required_message("/"))
        return None

    persona_name = frozen_persona_name or get_current_persona_name(user_id)
    session_id = frozen_session_id or ensure_session(user_id, persona_name)
    if session_id is None:
        await update.message.reply_text(build_retry_message())
        return None
    if not internal_call:
        remaining = get_remaining_tokens(user_id, persona_name)
        if remaining is not None and remaining <= 0:
            await update.message.reply_text(build_token_limit_reached_message("/", persona_name))
            return None
    await _set_typing_feedback(update, context, ctx)
    return {"user_id": user_id, "ctx": ctx, "settings": settings, "persona_name": persona_name, "session_id": session_id, "conversation": list(get_conversation(session_id)), "user_content": user_content, "save_msg": save_msg}
