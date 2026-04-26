"""Per-message context model for OneBot/QQ handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import QQ_STATE_DIR


@dataclass
class OneBotMessageContext:
    runtime: "OneBotRuntime"
    peer_id: str
    reply_to_id: str
    local_user_id: int
    local_chat_id: int
    session_user_id: int = 0
    is_group: bool = False
    group_id: str | None = None
    context_token: str | None = None
    inbound_key: str | None = None
    raw_event: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.session_user_id == 0:
            self.session_user_id = self.local_user_id

    @property
    def log_context(self) -> str:
        return f"[onebot:{self.local_user_id}]"

    @property
    def is_admin(self) -> bool:
        from .config import QQ_ADMIN_IDS
        return self.local_user_id in QQ_ADMIN_IDS

    async def reply_text(self, text: str) -> None:
        await self.runtime.send_text_to_peer(
            self.reply_to_id,
            text,
            is_group=self.is_group,
            dedupe_key=self.inbound_key,
        )

    async def reply_file(self, file_path: str | Path, *, caption: str = "") -> None:
        await self.runtime.send_file_to_peer(
            self.reply_to_id,
            str(file_path),
            caption=caption,
            is_group=self.is_group,
            dedupe_key=self.inbound_key,
        )

    @property
    def export_dir(self) -> str:
        return str(Path(QQ_STATE_DIR) / "exports")
