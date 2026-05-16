"""OneBot OutboundSender — writes bytes to tmp file and delegates to runtime."""

from __future__ import annotations

import os
import tempfile

from platforms.shared.outbound import OutboundSender


class OneBotOutbound(OutboundSender):
    def __init__(self, ctx):
        self.ctx = ctx

    async def _send(self, data: bytes, *, filename: str, caption: str, kind: str) -> None:
        fd, tmp = tempfile.mkstemp(suffix="_" + filename)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            await self.ctx.runtime.send_file_to_peer(
                self.ctx.reply_to_id,
                tmp,
                caption=caption,
                is_group=self.ctx.is_group,
                dedupe_key=self.ctx.inbound_key,
                kind=kind,
            )
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    async def send_image(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self._send(data, filename=filename or "image.png", caption=caption, kind="image")

    async def send_document(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self._send(data, filename=filename or "file.bin", caption=caption, kind="file")

    async def send_voice(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self._send(data, filename=filename or "voice.mp3", caption=caption, kind="record")

    async def send_video(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self._send(data, filename=filename or "video.mp4", caption=caption, kind="video")
