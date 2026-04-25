"""Inbound envelope model for OneBot/QQ messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OneBotInboundEnvelope:
    """Represents a parsed inbound event from NapCat (OneBot 11)."""

    message: dict
    inbound_key: str | None
    from_user_id: str
    to_user_id: str
    group_id: str | None
    reply_to_id: str
    text_body: str
    normalized_text: str
    raw_event: dict
    post_type: str
    message_type: str
    sub_type: str
    message_id: int
    user_id: int
    self_id: int

    @property
    def is_group(self) -> bool:
        return bool(self.group_id) and self.message_type == "group"

    @property
    def is_private(self) -> bool:
        return self.message_type == "private"

    @property
    def echo_target_id(self) -> str:
        return self.group_id or self.from_user_id or ""
