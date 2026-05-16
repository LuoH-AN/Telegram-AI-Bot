"""File/media delivery for OneBot via CQ codes (base64 inline).

Supports send_file_to_peer with kind hint OR extension-based inference,
choosing CQ:image / CQ:record / CQ:video / CQ:file segments.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from ..config import logger, ONEBOT_MODE


_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_VID_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
_VOICE_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".amr", ".silk"}


def _infer_cq_type(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in _IMG_EXTS:
        return "image"
    if suf in _VID_EXTS:
        return "video"
    if suf in _VOICE_EXTS:
        return "record"
    return "file"


def _build_segment(cq_type: str, data: bytes, filename: str) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    if cq_type == "file":
        return f"[CQ:file,file=base64://{b64},name={filename}]"
    return f"[CQ:{cq_type},file=base64://{b64}]"


class RuntimeSendFileMixin:
    async def send_file_to_peer(
        self,
        peer_id: str,
        file_path: str,
        *,
        caption: str = "",
        is_group: bool = False,
        dedupe_key: str | None = None,
        kind: str | None = None,
    ) -> None:
        path = Path(file_path)
        data = await asyncio.to_thread(path.read_bytes)
        cq_type = kind or _infer_cq_type(path)
        if cq_type == "document":
            cq_type = "file"
        segment = _build_segment(cq_type, data, path.name)
        message = segment + (f"\n{caption}" if caption and cq_type != "file" else "")

        outbound_key = f"file:{peer_id}:{dedupe_key}:{path.name}:{caption}" if dedupe_key else None
        if outbound_key and self._sent_messages.remember_once(outbound_key):
            logger.info("Skipping duplicate OneBot outbound file: peer=%s key=%s", peer_id, dedupe_key)
            return

        logger.info(
            "OneBot outbound file: peer=%s is_group=%s kind=%s name=%s size=%d",
            peer_id, is_group, cq_type, path.name, len(data),
        )
        self._recent_outbound_fingerprints.remember(
            self._outbound_fingerprint(target_id=peer_id, text=caption or "")
        )
        await self._send_message_payload(peer_id, is_group, message)

    async def _send_message_payload(self, peer_id: str, is_group: bool, message: str) -> None:
        if ONEBOT_MODE == "ws":
            bridge = getattr(self, "_ws_bridge", None)
            if bridge is None or not bridge.connected:
                raise RuntimeError("OneBot WebSocket bridge is not connected")
            action = "send_group_msg" if is_group else "send_private_msg"
            key = "group_id" if is_group else "user_id"
            await bridge._send_api(action, {key: int(peer_id), "message": message})
            return
        if not self.client.connected:
            raise RuntimeError("OneBot client is not connected")
        if is_group:
            await self.client.send_group_msg(int(peer_id), message)
        else:
            await self.client.send_private_msg(int(peer_id), message)
