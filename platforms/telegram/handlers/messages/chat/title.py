"""Session title generation helpers."""

from __future__ import annotations

import logging

from cache import cache
from services import generate_session_title
from utils.platform import format_log_context

logger = logging.getLogger(__name__)


async def generate_and_set_title(
    user_id: int,
    session_id: int,
    user_message: str,
    ai_response: str,
) -> None:
    try:
        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            sctx = format_log_context(platform="telegram", user_id=user_id, scope="system", chat_id=0)
            logger.info("%s auto-generated session title: %s", sctx, title)
    except Exception as exc:
        sctx = format_log_context(platform="telegram", user_id=user_id, scope="system", chat_id=0)
        logger.warning("%s failed to auto-generate title: %s", sctx, exc)
