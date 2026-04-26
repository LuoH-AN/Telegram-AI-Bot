"""Inbound dedupe and message parsing for OneBot events."""

from __future__ import annotations

import hashlib

from ..config import logger
from ..envelope import OneBotInboundEnvelope


class RuntimeIdentMixin:
    def _message_dedup_key(self, message_id: int, user_id: int, group_id: int | None, text: str) -> str:
        if message_id:
            return f"onebot:msgid:{message_id}"
        body_hash = hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]
        return f"onebot:fallback:{user_id}:{group_id}:{body_hash}"

    def _outbound_fingerprint(self, target_id: str, text: str = "") -> str:
        body = (text or "").strip()
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:16] if body else "no-body"
        return f"{target_id}|text|{digest}"

    def _parse_event(self, event: dict) -> OneBotInboundEnvelope:
        """Parse a OneBot 11 event into our envelope model."""
        post_type = str(event.get("post_type", ""))
        message_type = str(event.get("message_type", ""))
        sub_type = str(event.get("sub_type", ""))

        if post_type == "message":
            return self._parse_message_event(event, post_type, message_type, sub_type)
        elif post_type == "meta_event":
            logger.debug("Ignoring meta_event: %s", event.get("meta_event_type"))
            raise ValueError("meta_event ignored")
        elif post_type == "notice":
            logger.debug("Ignoring notice: %s", event.get("notice_type"))
            raise ValueError("notice ignored")
        else:
            logger.debug("Unknown post_type: %s", post_type)
            raise ValueError(f"Unknown post_type: {post_type}")

    def _parse_message_event(self, event: dict, post_type: str = "", sub_type: str = "") -> OneBotInboundEnvelope:
        """Parse a message event from OneBot 11."""
        raw_message = event.get("message", []) or []
        if isinstance(raw_message, list):
            text_body = "".join(
                seg.get("data", {}).get("text", "")
                for seg in raw_message
                if seg.get("type") == "text"
            )
            raw_message_str = str(raw_message)
        else:
            text_body = str(raw_message)
            raw_message_str = raw_message

        message_id = int(event.get("message_id") or 0)
        user_id = int(event.get("user_id") or 0)
        group_id_val = event.get("group_id")
        group_id = str(group_id_val) if group_id_val else None
        group_id_int = int(group_id_val) if group_id_val else 0

        message_type = str(event.get("message_type", ""))
        from_user_id = str(user_id)
        to_user_id = str(event.get("target_id") or "")
        self_id = int(event.get("self_id") or 0)

        dedupe_key = self._message_dedup_key(
            message_id=message_id,
            user_id=user_id,
            group_id=group_id_int or None,
            text=text_body,
        )

        return OneBotInboundEnvelope(
            message={"raw": event, "message_list": raw_message if isinstance(raw_message, list) else [raw_message]},
            inbound_key=dedupe_key,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            group_id=group_id,
            reply_to_id=from_user_id if message_type == "private" else str(group_id_int),
            text_body=text_body,
            normalized_text=text_body,
            raw_event=event,
            post_type=post_type,
            message_type=message_type,
            sub_type=sub_type,
            message_id=message_id,
            user_id=user_id,
            self_id=self_id,
        )

    def _should_skip_echo(self, inbound: OneBotInboundEnvelope) -> bool:
        """Skip messages sent by ourselves."""
        if inbound.user_id == inbound.self_id:
            return True
        fingerprint = self._outbound_fingerprint(
            target_id=inbound.echo_target_id,
            text=inbound.text_body,
        )
        if self._recent_outbound_fingerprints.seen(fingerprint):
            logger.info("Skipping self-echo: message_id=%s", inbound.message_id)
            return True
        return False
