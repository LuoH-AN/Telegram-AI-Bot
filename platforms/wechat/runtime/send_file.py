"""File/media delivery helpers."""

from __future__ import annotations

import asyncio

from ..config import logger
from ..message.extract import wechat_media_type_code_for_path


class RuntimeSendFileMixin:
    async def send_file_to_peer(
        self,
        peer_id: str,
        file_path: str,
        *,
        caption: str = "",
        context_token: str | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        state = self.client.state_store.load()
        if not state.token:
            raise RuntimeError("WeChat bot is not logged in")
        context = context_token or self.client.state_store.resolve_context_token(peer_id)
        outbound_key = f"file:{peer_id}:{dedupe_key}:{file_path}:{caption}" if dedupe_key else None
        if self._sent_messages.remember_once(outbound_key):
            logger.info("Skipping duplicate WeChat outbound file: peer=%s dedupe_key=%s path=%s", peer_id, dedupe_key, file_path)
            return
        logger.info("WeChat outbound file: peer=%s dedupe_key=%s path=%s", peer_id, dedupe_key, file_path)
        media_type_code = wechat_media_type_code_for_path(file_path)
        self._recent_outbound_fingerprints.remember(
            self._outbound_fingerprint(target_id=peer_id, text=caption or "", item_types=(media_type_code,))
        )
        await asyncio.to_thread(
            self.client.send_media_file,
            state.token,
            peer_id,
            file_path,
            context_token=context,
            text=caption,
        )
