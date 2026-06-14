"""Preflight validation for media handlers."""

from telegram import Update
from telegram.ext import ContextTypes

from adapters.telegram.rich_text import reply_rich_text
from domain.services import ensure_session, get_current_persona_name, get_remaining_tokens, has_api_key
from domain.services.refresh import ensure_user_state
from shared.utils.platform import build_api_key_required_message, build_retry_message, build_token_limit_reached_message

from .group import build_media_caption, collect_media_group_messages
from .log import should_respond_in_group
from .types import MediaRequestContext


async def preflight_media_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> MediaRequestContext | None:
    if not await should_respond_in_group(update, context):
        return None

    message = update.effective_message
    if message is None:
        return None
    grouped_messages = await collect_media_group_messages(message)
    if grouped_messages is None:
        return None
    if any(message.forward_origin for message in grouped_messages):
        return None

    user_id = update.effective_user.id
    await ensure_user_state(user_id)
    if not has_api_key(user_id):
        await reply_rich_text(message, build_api_key_required_message("/"))
        return None

    persona_name = get_current_persona_name(user_id)
    remaining = get_remaining_tokens(user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await reply_rich_text(message, build_token_limit_reached_message("/", persona_name))
        return None

    session_id = ensure_session(user_id, persona_name)
    if session_id is None:
        await reply_rich_text(message, build_retry_message())
        return None

    caption = build_media_caption(
        grouped_messages,
        bot_username=context.bot.username,
        reply_message=message.reply_to_message,
    )
    return MediaRequestContext(
        grouped_messages=grouped_messages,
        caption=caption,
        persona_name=persona_name,
        session_id=session_id,
    )
