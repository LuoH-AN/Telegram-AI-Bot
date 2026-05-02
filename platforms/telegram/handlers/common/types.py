"""Shared dataclasses for handler helpers."""

from dataclasses import dataclass

from telegram import Message


@dataclass(frozen=True)
class MediaRequestContext:
    grouped_messages: list[Message]
    caption: str
    persona_name: str
    session_id: int

