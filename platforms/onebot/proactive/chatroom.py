"""Build chatroom-style LLM user content for proactive group replies."""

from __future__ import annotations

from datetime import datetime

from .buffer import get_recent_lines

DIRECT_REASONS = {"at-mention", "reply-to-bot", "alias"}

_CHATROOM_INSTRUCTION = (
    "You are a casual participant in this group chat, not a Q&A assistant. "
    "React to the new incoming message naturally, as if you were one of the members. "
    "Keep it short and in the SAME language the chat is using. "
    "Do not introduce yourself, do not list options, do not use bullet points."
)


def is_direct_trigger(reason: str) -> bool:
    return reason in DIRECT_REASONS


def build_chatroom_user_content(
    *,
    group_id: int,
    nickname: str,
    new_text: str,
) -> str:
    history = get_recent_lines(int(group_id), exclude_last=1)
    chat_block = "\n".join(history) if history else "(no recent messages)"
    ts = datetime.now().strftime("%H:%M:%S")
    nick = (nickname or "User").strip() or "User"
    return (
        "You are observing a group chat. Recent messages:\n"
        f"{chat_block}\n\n"
        f"New incoming message — [{nick}/{ts}]: {new_text}\n\n"
        f"{_CHATROOM_INSTRUCTION}"
    )
