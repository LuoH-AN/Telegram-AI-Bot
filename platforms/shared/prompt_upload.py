"""Detect 'set prompt from file' commands carried in a message caption/text.

Used by Telegram/WeChat/OneBot inbound paths to recognize captions like
``/persona prompt`` or ``/set global_prompt`` so an attached .txt file's
contents become the new prompt instead of regular chat content.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.persona import apply_global_prompt_from_text, apply_persona_prompt_from_text

PROMPT_TARGET_PERSONA = "persona"
PROMPT_TARGET_GLOBAL = "global"


@dataclass(frozen=True)
class PromptUploadCommand:
    target: str
    command_prefix: str


_SUPPORTED_PREFIXES = ("/", "!", ".", "#")


def _normalize(text: str) -> tuple[str, str] | None:
    body = (text or "").strip()
    if not body:
        return None
    for prefix in _SUPPORTED_PREFIXES:
        if body.startswith(prefix):
            return body[len(prefix):].strip(), prefix
    return None


def parse_prompt_upload_caption(caption: str) -> PromptUploadCommand | None:
    parsed = _normalize(caption)
    if not parsed:
        return None
    body, prefix = parsed
    tokens = body.split()
    if len(tokens) != 2:
        return None
    head, sub = tokens[0].lower(), tokens[1].lower()
    if head == "persona" and sub == "prompt":
        return PromptUploadCommand(target=PROMPT_TARGET_PERSONA, command_prefix=prefix)
    if head == "set" and sub == "global_prompt":
        return PromptUploadCommand(target=PROMPT_TARGET_GLOBAL, command_prefix=prefix)
    return None


def apply_prompt_upload(command: PromptUploadCommand, user_id: int, text: str) -> str:
    if command.target == PROMPT_TARGET_GLOBAL:
        return apply_global_prompt_from_text(user_id, text)
    return apply_persona_prompt_from_text(user_id, text)
