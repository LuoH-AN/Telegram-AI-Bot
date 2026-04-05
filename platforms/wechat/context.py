"""Per-message context model for WeChat handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import WECHAT_STATE_DIR, wechat_ctx_for_scope


@dataclass
class WeChatMessageContext:
    runtime: "WeChatBotRuntime"
    peer_id: str
    reply_to_id: str
    local_user_id: int
    local_chat_id: int
    is_group: bool = False
    group_id: str | None = None
    context_token: str | None = None
    inbound_key: str | None = None

    @property
    def log_context(self) -> str:
        return wechat_ctx_for_scope(
            local_user_id=self.local_user_id,
            local_chat_id=self.local_chat_id,
            is_group=self.is_group,
        )

    async def reply_text(self, text: str) -> None:
        await self.runtime.send_text_to_peer(
            self.reply_to_id,
            text,
            context_token=self.context_token,
            dedupe_key=self.inbound_key,
        )

    async def reply_file(self, file_path: str | Path, *, caption: str = "") -> None:
        await self.runtime.send_file_to_peer(
            self.reply_to_id,
            str(file_path),
            caption=caption,
            context_token=self.context_token,
            dedupe_key=self.inbound_key,
        )

    @property
    def export_dir(self) -> str:
        return str(Path(WECHAT_STATE_DIR) / "exports")
