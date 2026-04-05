"""Auto title generation for new WeChat sessions."""

from __future__ import annotations

import logging

from cache import cache
from services import generate_session_title

from ..config import wechat_ctx

logger = logging.getLogger(__name__)


async def generate_and_set_title(user_id: int, session_id: int, user_message: str, ai_response: str) -> None:
    try:
        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            logger.info("%s auto-generated session title: %s", wechat_ctx(user_id), title)
    except Exception as exc:
        logger.warning("%s failed to auto-generate title: %s", wechat_ctx(user_id), exc)
