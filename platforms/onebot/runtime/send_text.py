"""Text delivery helpers for OneBot."""

from __future__ import annotations

from utils.format import split_message

from ..config import logger


class RuntimeSendTextMixin:
    async def send_text_to_peer(
        self,
        peer_id: str,
        text: str,
        *,
        is_group: bool = False,
        dedupe_key: str | None = None,
    ) -> None:
        """Send text to a QQ user or group."""
        if not self.client.connected:
            raise RuntimeError("OneBot client is not connected")

        chunks = split_message(text or "(Empty response)", max_length=4000)
        for index, chunk in enumerate(chunks or ["(Empty response)"]):
            outbound_key = f"text:{peer_id}:{dedupe_key}:{index}" if dedupe_key else None
            if outbound_key and self._sent_messages.remember_once(outbound_key):
                logger.info("Skipping duplicate OneBot outbound: peer=%s dedupe_key=%s", peer_id, dedupe_key)
                continue

            logger.info("OneBot outbound: peer=%s is_group=%s index=%s len=%s", peer_id, is_group, index, len(chunk))
            self._recent_outbound_fingerprints.remember(self._outbound_fingerprint(target_id=peer_id, text=chunk))

            try:
                if is_group:
                    await self.client.send_group_msg(int(peer_id), chunk)
                else:
                    await self.client.send_private_msg(int(peer_id), chunk)
            except Exception:
                logger.exception("Failed to send OneBot message to %s", peer_id)