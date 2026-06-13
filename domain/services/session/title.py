"""Session title generation via AI client."""

import asyncio
import logging

from infrastructure.config import TITLE_GENERATION_PROMPT

logger = logging.getLogger(__name__)


async def generate_session_title(user_id: int, user_message: str, ai_response: str) -> str | None:
    try:
        from domain.services.user import get_user_settings
        from domain.services.cron import _create_task_client

        settings = get_user_settings(user_id)
        client, title_model = _create_task_client(user_id, settings.get("title_model", ""), settings)
        prompt = TITLE_GENERATION_PROMPT.format(
            user_message=user_message[:500],
            ai_response=ai_response[:500],
        )
        chunks = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: list(
                client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model=title_model,
                    temperature=0.3,
                    stream=False,
                )
            ),
        )
        if not chunks:
            return None

        title = "".join(chunk.content for chunk in chunks if chunk.content).strip()
        if not title:
            return None
        if title.startswith("```"):
            lines = title.split("\n")
            title = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
        title = title.strip('"').strip("'").strip()
        return title if title and len(title) < 50 else None
    except Exception as exc:
        logger.warning("Failed to generate session title: %s", exc)
        return None


async def generate_title_for_session(user_id: int, session_id: int) -> str | None:
    from infrastructure.cache import cache

    messages = cache.get_conversation_by_session(session_id)
    user_msg = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    ai_msg = next((m.get("content", "") for m in messages if m.get("role") == "assistant"), "")
    if not user_msg and not ai_msg:
        return None
    return await generate_session_title(user_id, user_msg, ai_msg)
