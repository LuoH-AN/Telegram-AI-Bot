"""Session management service."""

import json
import logging

from cache import cache
from config import TITLE_GENERATION_PROMPT

logger = logging.getLogger(__name__)


def get_sessions(user_id: int, persona_name: str = None) -> list[dict]:
    """Get all sessions for a user's current or specified persona."""
    return cache.get_sessions(user_id, persona_name)


def get_current_session(user_id: int, persona_name: str = None) -> dict | None:
    """Get the current session dict for a persona."""
    session_id = get_current_session_id(user_id, persona_name)
    if session_id is None:
        return None
    return cache.get_session_by_id(session_id)


def get_current_session_id(user_id: int, persona_name: str = None) -> int | None:
    """Get the current session ID for a persona."""
    if persona_name is None:
        persona_name = cache.get_current_persona_name(user_id)
    return cache.get_current_session_id(user_id, persona_name)


def create_session(user_id: int, persona_name: str = None, title: str = None) -> dict:
    """Create a new session and switch to it."""
    if persona_name is None:
        persona_name = cache.get_current_persona_name(user_id)
    session = cache.create_session(user_id, persona_name, title)
    cache.set_current_session_id(user_id, persona_name, session["id"])
    return session


def delete_session(user_id: int, session_index: int, persona_name: str = None) -> bool:
    """Delete a session by 1-based index. Returns False if index invalid."""
    if persona_name is None:
        persona_name = cache.get_current_persona_name(user_id)
    sessions = cache.get_sessions(user_id, persona_name)
    if session_index < 1 or session_index > len(sessions):
        return False

    session = sessions[session_index - 1]
    session_id = session["id"]
    current_id = cache.get_current_session_id(user_id, persona_name)

    cache.delete_session(session_id, user_id, persona_name)

    # If we deleted the current session, switch to the most recent remaining
    if current_id == session_id:
        remaining = cache.get_sessions(user_id, persona_name)
        if remaining:
            cache.set_current_session_id(user_id, persona_name, remaining[-1]["id"])
        else:
            # Auto-create a new session
            new_session = cache.create_session(user_id, persona_name)
            cache.set_current_session_id(user_id, persona_name, new_session["id"])

    return True


def switch_session(user_id: int, session_index: int, persona_name: str = None) -> bool:
    """Switch to a session by 1-based index. Returns False if index invalid."""
    if persona_name is None:
        persona_name = cache.get_current_persona_name(user_id)
    sessions = cache.get_sessions(user_id, persona_name)
    if session_index < 1 or session_index > len(sessions):
        return False

    session = sessions[session_index - 1]
    cache.set_current_session_id(user_id, persona_name, session["id"])
    return True


def rename_session(user_id: int, title: str, persona_name: str = None) -> bool:
    """Rename the current session. Returns False if no current session."""
    session_id = get_current_session_id(user_id, persona_name)
    if session_id is None:
        return False
    cache.update_session_title(session_id, title)
    return True


def get_session_count(user_id: int, persona_name: str = None) -> int:
    """Get the number of sessions for a persona."""
    return len(cache.get_sessions(user_id, persona_name))


def get_session_message_count(session_id: int) -> int:
    """Get the number of messages in a specific session."""
    return len(cache.get_conversation_by_session(session_id))


async def generate_session_title(user_id: int, user_message: str, ai_response: str) -> str | None:
    """Generate a title for the current session using AI.

    title_model format: "provider:model" or just "model".
    When provider is specified, uses that provider's api_key/base_url from presets.
    Otherwise uses the current provider.

    Returns the generated title or None on failure.
    """
    try:
        from ai.openai_client import create_openai_client
        from services.user_service import get_user_settings

        settings = get_user_settings(user_id)

        # Parse title_model — supports "provider:model" or just "model"
        title_model_raw = settings.get("title_model", "")
        api_key = settings["api_key"]
        base_url = settings["base_url"]
        title_model = settings.get("model", "gpt-4o")

        if title_model_raw:
            if ":" in title_model_raw:
                provider_name, model_name = title_model_raw.split(":", 1)
                presets = settings.get("api_presets", {})
                # Case-insensitive provider lookup
                preset = None
                for k, v in presets.items():
                    if k.lower() == provider_name.lower():
                        preset = v
                        break
                if preset:
                    api_key = preset["api_key"]
                    base_url = preset["base_url"]
                    title_model = model_name or preset.get("model", title_model)
                else:
                    logger.warning("Title generation provider '%s' not found in presets", provider_name)
                    return None
            else:
                title_model = title_model_raw

        # Build the prompt
        prompt = TITLE_GENERATION_PROMPT.format(
            user_message=user_message[:500],
            ai_response=ai_response[:500],
        )

        client = create_openai_client(api_key=api_key, base_url=base_url)

        # Non-streaming call with low temperature
        import asyncio
        loop = asyncio.get_event_loop()
        chunks = await loop.run_in_executor(
            None,
            lambda: list(client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=title_model,
                temperature=0.3,
                stream=False,
            ))
        )

        if not chunks:
            return None

        response_text = ""
        for chunk in chunks:
            if chunk.content:
                response_text += chunk.content

        if not response_text:
            return None

        # Try to parse JSON response
        response_text = response_text.strip()
        # Handle possible markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            response_text = response_text.strip()

        try:
            data = json.loads(response_text)
            if isinstance(data, dict):
                # Try "title" key (case-insensitive)
                title = None
                for k, v in data.items():
                    if k.lower() == "title" and v:
                        title = str(v).strip()
                        break
                if title:
                    return title
            elif isinstance(data, str) and data.strip():
                # Model returned a JSON string like "some title"
                title = data.strip()
                if len(title) < 50:
                    return title
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: use raw text, strip quotes
        title = response_text.strip().strip('"').strip("'").strip()
        # Reject if it looks like unparsed JSON or is too generic
        if title and len(title) < 50 and not title.startswith("{"):
            return title

        return None

    except Exception as e:
        logger.warning("Failed to generate session title: %s", e)
        return None
