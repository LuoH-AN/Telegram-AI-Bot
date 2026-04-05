"""Inbound dedupe and echo-suppression helpers."""

from __future__ import annotations

import hashlib

from ..config import logger
from ..envelope import WeChatInboundEnvelope
from ..message.extract import extract_text_body, strip_wechat_group_mentions


class RuntimeIdentMixin:
    def _message_dedup_key(
        self,
        *,
        message_id: str,
        seq: str,
        create_time_ms: str,
        from_user_id: str,
        to_user_id: str,
        group_id: str | None,
        text_body: str,
    ) -> str | None:
        if message_id:
            return f"msgid:{message_id}"
        if seq and from_user_id:
            return f"seq:{seq}:from:{from_user_id}"
        if from_user_id and create_time_ms:
            body_hash = hashlib.sha1(text_body.encode("utf-8")).hexdigest()[:16] if text_body else "no-body"
            return f"fallback:{from_user_id}:{to_user_id}:{group_id}:{create_time_ms}:{body_hash}"
        return None

    def _outbound_fingerprint(self, *, target_id: str, text: str = "", item_types: tuple[int, ...] = ()) -> str:
        body = text.strip()
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:16] if body else "no-body"
        types = ",".join(str(item) for item in item_types) if item_types else "text"
        return f"{target_id}|{types}|{digest}"

    def _parse_inbound_message(self, message: dict) -> WeChatInboundEnvelope:
        from_user_id = str(message.get("from_user_id") or "").strip()
        to_user_id = str(message.get("to_user_id") or "").strip()
        group_id = str(message.get("group_id") or "").strip() or None
        text_body = extract_text_body(message.get("item_list") or [])
        normalized = strip_wechat_group_mentions(text_body) if group_id else text_body
        message_id = str(message.get("message_id") or "").strip()
        seq = str(message.get("seq") or "").strip()
        inbound_key = self._message_dedup_key(
            message_id=message_id,
            seq=seq,
            create_time_ms=str(message.get("create_time_ms") or "").strip(),
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            group_id=group_id,
            text_body=text_body,
        )
        return WeChatInboundEnvelope(
            message=message,
            inbound_key=inbound_key,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            group_id=group_id,
            reply_to_id=group_id or from_user_id,
            text_body=text_body,
            normalized_text=normalized,
            item_types=tuple(int(item.get("type") or 0) for item in (message.get("item_list") or [])),
            message_type=int(message.get("message_type") or 1),
            message_state=int(message.get("message_state") or 0),
            message_id=message_id,
            seq=seq,
        )

    def _should_skip_inbound_echo(self, inbound: WeChatInboundEnvelope, current_user_id: str) -> bool:
        if not current_user_id or inbound.from_user_id != current_user_id:
            return False
        fingerprint = self._outbound_fingerprint(target_id=inbound.echo_target_id, text=inbound.text_body, item_types=inbound.item_types or (1,))
        if self._recent_outbound_fingerprints.seen(fingerprint):
            logger.info("Skipping outbound echo WeChat message: message_id=%s seq=%s state=%s", inbound.message_id, inbound.seq, inbound.message_state)
            return True
        logger.warning("WeChat self-sent message did not match recent outbound fingerprint; processing continues.")
        return False
