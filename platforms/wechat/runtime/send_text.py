"""Text delivery helpers.

Uses the wechatbot-sdk's send/reply methods instead of raw HTTP calls.
"""

from __future__ import annotations

from utils.format import split_message

from ..config import logger


class RuntimeSendTextMixin:
    async def send_text_to_peer(
        self,
        peer_id: str,
        text: str,
        *,
        context_token: str | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        state = self.client.state_store.load()
        if not (state.token or self.client.get_credentials()):
            raise RuntimeError("WeChat bot is not logged in")
        resolved_context_token = context_token or self.client.state_store.resolve_context_token(peer_id)
        chunks = split_message(text or "(Empty response)", max_length=4000)
        for index, chunk in enumerate(chunks or ["(Empty response)"]):
            outbound_key = f"text:{peer_id}:{dedupe_key}:{index}" if dedupe_key else None
            if self._sent_messages.remember_once(outbound_key):
                logger.info("Skipping duplicate WeChat outbound text: peer=%s dedupe_key=%s index=%s", peer_id, dedupe_key, index)
                continue
            logger.info("WeChat outbound text: peer=%s dedupe_key=%s index=%s len=%s", peer_id, dedupe_key, index, len(chunk))
            self._recent_outbound_fingerprints.remember(self._outbound_fingerprint(target_id=peer_id, text=chunk, item_types=(1,)))
            await self.client.send_text(peer_id, chunk, context_token=resolved_context_token)

    async def send_wechat_text(self, local_user_id: int, text: str) -> None:
        peer_id = self.client.state_store.resolve_peer(local_user_id)
        if not peer_id:
            raise RuntimeError(f"WeChat peer mapping not found for local user {local_user_id}")
        await self.send_text_to_peer(peer_id, text)
