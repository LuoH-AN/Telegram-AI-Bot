"""Inbound envelope model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WeChatInboundEnvelope:
    message: dict
    inbound_key: str | None
    from_user_id: str
    to_user_id: str
    group_id: str | None
    reply_to_id: str
    text_body: str
    normalized_text: str
    item_types: tuple[int, ...]
    message_type: int
    message_state: int
    message_id: str
    seq: str

    @property
    def is_group(self) -> bool:
        return bool(self.group_id)

    @property
    def echo_target_id(self) -> str:
        return self.group_id or self.to_user_id or self.from_user_id
