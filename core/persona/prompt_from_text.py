"""Apply an uploaded text file as the user's persona or global prompt."""

from __future__ import annotations

from config import MAX_TEXT_CONTENT_LENGTH
from services import get_current_persona_name, update_current_prompt, update_user_setting


def apply_persona_prompt_from_text(user_id: int, text: str) -> str:
    prompt = (text or "").strip()
    if not prompt:
        return "Uploaded file is empty — prompt not updated."
    truncated = len(prompt) > MAX_TEXT_CONTENT_LENGTH
    if truncated:
        prompt = prompt[:MAX_TEXT_CONTENT_LENGTH]
    update_current_prompt(user_id, prompt)
    name = get_current_persona_name(user_id)
    suffix = f" (truncated to {MAX_TEXT_CONTENT_LENGTH} chars)" if truncated else ""
    return f"Updated prompt for `{name}` from uploaded file{suffix} ({len(prompt)} chars)."


def apply_global_prompt_from_text(user_id: int, text: str) -> str:
    prompt = (text or "").strip()
    if not prompt:
        update_user_setting(user_id, "global_prompt", "")
        return "Uploaded file is empty — global_prompt cleared."
    truncated = len(prompt) > MAX_TEXT_CONTENT_LENGTH
    if truncated:
        prompt = prompt[:MAX_TEXT_CONTENT_LENGTH]
    update_user_setting(user_id, "global_prompt", prompt)
    suffix = f" (truncated to {MAX_TEXT_CONTENT_LENGTH} chars)" if truncated else ""
    return f"Updated global_prompt from uploaded file{suffix} ({len(prompt)} chars)."
