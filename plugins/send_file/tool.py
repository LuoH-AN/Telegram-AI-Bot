"""send_file tool — AI sends media (image/document/voice/video) to active chat."""

from __future__ import annotations

import logging

from plugins.core.base import BasePlugin
from telegram_bot.outbound import get_outbound, send_sync

from . import sources

logger = logging.getLogger(__name__)

_VALID_KINDS = {"image", "document", "voice", "video"}
_VALID_SOURCES = {"url", "path", "generate"}


class SendFileTool(BasePlugin):
    @property
    def name(self) -> str:
        return "send_file"

    def definitions(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "send_file",
                "description": (
                    "Send a media message (image, document, voice, video) directly into the "
                    "current chat with the user. Only works during an active reply. "
                    "Source can be 'url' (download), 'path' (local file), or 'generate' "
                    "(AI-generated image from a prompt; image kind only)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": sorted(_VALID_KINDS),
                                 "description": "Media kind."},
                        "source": {"type": "string", "enum": sorted(_VALID_SOURCES),
                                   "description": "Where the bytes come from."},
                        "url": {"type": "string", "description": "URL when source=url."},
                        "path": {"type": "string", "description": "Local file path when source=path."},
                        "prompt": {"type": "string",
                                   "description": "Image generation prompt when source=generate."},
                        "filename": {"type": "string",
                                     "description": "Display filename (optional)."},
                        "caption": {"type": "string", "description": "Optional caption."},
                        "size": {"type": "string",
                                 "description": "Image size when source=generate, e.g. 1024x1024."},
                    },
                    "required": ["kind", "source"],
                },
            },
        }]

    def get_instruction(self) -> str:
        return (
            "\nsend_file usage:\n"
            "- Use for sending images/files to the user. Text answers should still go in the regular reply.\n"
            "- source='url' downloads first; 'path' reads a local file; 'generate' creates an image from prompt.\n"
            "- Max 50MB. Caption is optional and should be short.\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        kind = str(arguments.get("kind") or "").strip().lower()
        source = str(arguments.get("source") or "").strip().lower()
        if kind not in _VALID_KINDS:
            return f"Error: kind must be one of {sorted(_VALID_KINDS)}"
        if source not in _VALID_SOURCES:
            return f"Error: source must be one of {sorted(_VALID_SOURCES)}"
        if source == "generate" and kind != "image":
            return "Error: source='generate' only supported for kind='image'"
        if get_outbound() is None:
            return "Error: no active chat — send_file can only be used while replying"

        caption = str(arguments.get("caption") or "").strip()
        filename = str(arguments.get("filename") or "").strip() or None

        try:
            data, default_name = self._resolve(user_id, kind, source, arguments)
        except Exception as exc:
            logger.warning("send_file resolve failed: %s", exc)
            return f"Error: could not load source - {exc}"

        try:
            send_sync(kind, data, filename=filename or default_name, caption=caption)
        except Exception as exc:
            logger.exception("send_file delivery failed")
            return f"Error: send failed - {exc}"

        return f"Sent {kind} ({len(data)} bytes) as '{filename or default_name}'"

    def _resolve(self, user_id: int, kind: str, source: str, args: dict) -> tuple[bytes, str]:
        if source == "url":
            url = str(args.get("url") or "").strip()
            if not url:
                raise ValueError("url required when source=url")
            return sources.fetch_url(url, kind=kind)
        if source == "path":
            path = str(args.get("path") or "").strip()
            if not path:
                raise ValueError("path required when source=path")
            return sources.read_path(path, kind=kind)
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt required when source=generate")
        size = str(args.get("size") or "1024x1024").strip() or "1024x1024"
        return sources.generate_image(user_id, prompt, size=size)
