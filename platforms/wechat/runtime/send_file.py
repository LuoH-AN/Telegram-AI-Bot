"""File/media delivery helpers.

Uses the wechatbot-sdk's send_media method for image/file/video delivery.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import logger


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
        if not (state.token or self.client.get_credentials()):
            raise RuntimeError("WeChat bot is not logged in")
        resolved_context_token = context_token or self.client.state_store.resolve_context_token(peer_id)
        outbound_key = f"file:{peer_id}:{dedupe_key}:{file_path}:{caption}" if dedupe_key else None
        if self._sent_messages.remember_once(outbound_key):
            logger.info("Skipping duplicate WeChat outbound file: peer=%s dedupe_key=%s path=%s", peer_id, dedupe_key, file_path)
            return
        logger.info("WeChat outbound file: peer=%s dedupe_key=%s path=%s", peer_id, dedupe_key, file_path)
        path = Path(file_path)
        data = await asyncio.to_thread(path.read_bytes)
        name = path.name

        if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            content: dict = {"image": data}
            item_types = (2,)
        elif path.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".avi"):
            content = {"video": data, "caption": caption}
            item_types = (5,)
        else:
            content = {"file": data, "file_name": name, "caption": caption}
            item_types = (4,)

        self._recent_outbound_fingerprints.remember(
            self._outbound_fingerprint(target_id=peer_id, text=caption or "", item_types=item_types)
        )
        await self.client.send_media(peer_id, content, context_token=resolved_context_token)
