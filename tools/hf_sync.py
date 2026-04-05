"""HF object storage tool for AI."""

from __future__ import annotations

import json
import logging

from .base import BaseTool
from services.hf_sync import run_hf_sync_command

logger = logging.getLogger(__name__)
_VALID_ACTIONS = {"upload", "upload_text", "upload_b64", "list", "url", "delete"}


class HFSyncTool(BaseTool):
    @property
    def name(self) -> str:
        return "hf_sync"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "hf_sync",
                    "description": (
                        "Store content as objects in HuggingFace Dataset (S3-like object storage). "
                        "Uses the provided key directly (no forced folder). "
                        "Supports upload/upload_text/upload_b64/list/url/delete."
                    ),
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(_VALID_ACTIONS),
                    "description": "Action: upload/upload_text/upload_b64/list/url/delete",
                },
                "path": {
                    "type": "string",
                    "description": "Local file path for upload action",
                },
                "key": {
                    "type": "string",
                    "description": "Object key path (e.g. assets/cover.png). Preferred.",
                },
                "name": {
                    "type": "string",
                    "description": "Legacy alias of key. Kept for compatibility.",
                },
                "text": {
                    "type": "string",
                    "description": "Text payload for upload_text action",
                },
                "content_b64": {
                    "type": "string",
                    "description": "Base64 payload for upload_b64 action",
                },
                "content_type": {
                    "type": "string",
                    "description": "Optional MIME type for upload_b64 action",
                },
                "encrypt": {
                    "type": "boolean",
                    "description": "Encrypt object content (default: true)",
                },
            },
            "required": ["action"],
        }

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        action = str(arguments.get("action", "")).strip().lower()
        if action not in _VALID_ACTIONS:
            return f"Error: invalid action '{action}'. Allowed: {', '.join(sorted(_VALID_ACTIONS))}"

        payload = {
            "action": action,
            "path": arguments.get("path"),
            "key": arguments.get("key"),
            "name": arguments.get("name"),
            "text": arguments.get("text"),
            "content_b64": arguments.get("content_b64"),
            "content_type": arguments.get("content_type"),
            "encrypt": arguments.get("encrypt", True),
        }
        request = json.dumps(payload, ensure_ascii=False)
        logger.info("hf_sync object action: user=%d action=%s", user_id, action)
        try:
            result = run_hf_sync_command(user_id, request)
            return str(result.get("output") or "")
        except Exception as exc:
            logger.exception("hf_sync object action failed: %s", action)
            return f"Error: action '{action}' failed - {exc}"
