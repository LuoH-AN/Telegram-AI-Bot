"""Auto title generation for new sessions."""

from __future__ import annotations

import logging

from cache import cache
from services import generate_session_title

logger = logging.getLogger(__name__)


async def generate_and_set_title(
    user_id: int,
    session_id: int,
    user_message: str,
    ai_response: str,
    log_context: str | None = None,
) -> None:
    """Generate and set a title for a new session.

    Args:
        user_id: User ID for logging.
        session_id: Session ID to update.
        user_message: First user message.
        ai_response: AI response to the first message.
        log_context: Optional log context string. If None, uses default format.
    """
    ctx = log_context or f"[user:{user_id}]"
    try:
        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            logger.info("%s auto-generated session title: %s", ctx, title)
    except Exception as exc:
        logger.warning("%s failed to auto-generate title: %s", ctx, exc)