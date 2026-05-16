"""WeChat OutboundSender — bridges in-memory bytes to runtime.send_file_to_peer."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from platforms.shared.outbound import OutboundSender


_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_VID_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}


def _coerce(filename: str, kind: str) -> str:
    """Ensure filename's extension matches kind so the SDK infers correct media type."""
    name = filename or f"file.{kind}"
    suffix = Path(name).suffix.lower()
    if kind == "image" and suffix not in _IMG_EXTS:
        name = (Path(name).stem or "image") + ".png"
    elif kind == "video" and suffix not in _VID_EXTS:
        name = (Path(name).stem or "video") + ".mp4"
    elif kind == "voice" and suffix not in {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".amr"}:
        name = (Path(name).stem or "voice") + ".mp3"
    return name


class WeChatOutbound(OutboundSender):
    def __init__(self, ctx):
        self.ctx = ctx

    async def _send_bytes(self, data: bytes, filename: str, caption: str) -> None:
        fd, tmp = tempfile.mkstemp(suffix="_" + filename)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            await self.ctx.reply_file(tmp, caption=caption)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    async def send_image(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self._send_bytes(data, _coerce(filename, "image"), caption)

    async def send_document(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self._send_bytes(data, filename or "file.bin", caption)

    async def send_voice(self, data: bytes, *, filename: str, caption: str = "") -> None:
        # WeChat SDK has no explicit voice-type — fall through as file.
        await self._send_bytes(data, _coerce(filename, "voice"), caption)

    async def send_video(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self._send_bytes(data, _coerce(filename, "video"), caption)
