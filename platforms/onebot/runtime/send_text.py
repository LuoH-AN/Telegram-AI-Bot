"""Text delivery helpers for OneBot."""

from __future__ import annotations

import asyncio
import math
import os
import random

from utils.format import markdown_to_plain, split_into_lines, split_message

from ..config import logger, ONEBOT_MODE


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


SEG_INTERVAL_MIN = _env_float("QQ_SEG_INTERVAL_MIN", 0.8)
SEG_INTERVAL_MAX = _env_float("QQ_SEG_INTERVAL_MAX", 2.2)
SEG_LOG_BASE = max(1.5, _env_float("QQ_SEG_LOG_BASE", 2.6))
SEG_METHOD = (os.getenv("QQ_SEG_METHOD") or "log").strip().lower()


def _word_count(text: str) -> int:
    if not text:
        return 0
    if all(ord(c) < 128 for c in text):
        return len(text.split()) or 1
    return sum(1 for c in text if c.isalnum()) or 1


def _segment_delay(text: str) -> float:
    if SEG_METHOD == "random":
        return random.uniform(SEG_INTERVAL_MIN, SEG_INTERVAL_MAX)
    base = math.log(_word_count(text) + 1, SEG_LOG_BASE)
    base = max(SEG_INTERVAL_MIN, min(SEG_INTERVAL_MAX, base))
    return base + random.uniform(0.0, 0.5)


def _build_segments(text: str, *, chat_reply: bool, is_group: bool) -> list[str]:
    if chat_reply and is_group:
        lines = split_into_lines(text)
        if lines:
            return lines
    return split_message(text or "(Empty response)", max_length=4000)


class RuntimeSendTextMixin:
    async def send_text_to_peer(
        self,
        peer_id: str,
        text: str,
        *,
        is_group: bool = False,
        dedupe_key: str | None = None,
        chat_reply: bool = False,
    ) -> None:
        """Send text to a QQ user or group."""
        text = markdown_to_plain(text) if text else text
        segments = _build_segments(text or "", chat_reply=chat_reply, is_group=is_group)
        natural = chat_reply and is_group
        send_fn = self._make_send_fn(is_group, peer_id)
        await self._stream_segments(peer_id, is_group, segments, dedupe_key, natural, send_fn)

    def _make_send_fn(self, is_group: bool, peer_id: str):
        if ONEBOT_MODE == "ws":
            bridge = getattr(self, "_ws_bridge", None)
            if bridge is None or not bridge.connected:
                raise RuntimeError("OneBot WebSocket bridge is not connected")
            api = "send_group_msg" if is_group else "send_private_msg"
            key = "group_id" if is_group else "user_id"

            async def _send(chunk: str) -> None:
                await bridge._send_api(api, {key: int(peer_id), "message": chunk})
            return _send

        if not self.client.connected:
            raise RuntimeError("OneBot client is not connected")

        async def _send(chunk: str) -> None:
            if is_group:
                await self.client.send_group_msg(int(peer_id), chunk)
            else:
                await self.client.send_private_msg(int(peer_id), chunk)
        return _send

    async def _stream_segments(
        self,
        peer_id: str,
        is_group: bool,
        segments: list[str],
        dedupe_key: str | None,
        natural: bool,
        send_fn,
    ) -> None:
        for index, chunk in enumerate(segments or ["(Empty response)"]):
            outbound_key = f"text:{peer_id}:{dedupe_key}:{index}" if dedupe_key else None
            if outbound_key and self._sent_messages.remember_once(outbound_key):
                logger.info("Skipping duplicate OneBot outbound: peer=%s dedupe_key=%s", peer_id, dedupe_key)
                continue
            if natural:
                await asyncio.sleep(_segment_delay(chunk))
            logger.info("OneBot outbound: peer=%s is_group=%s index=%s len=%s", peer_id, is_group, index, len(chunk))
            self._recent_outbound_fingerprints.remember(self._outbound_fingerprint(target_id=peer_id, text=chunk))
            try:
                await send_fn(chunk)
            except Exception:
                logger.exception("Failed to send OneBot message to %s", peer_id)
