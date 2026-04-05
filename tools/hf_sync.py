"""S3-style object storage tool for AI."""

from __future__ import annotations

import json
import logging

from .base import BaseTool
from services.hf_sync import run_hf_sync_command

logger = logging.getLogger(__name__)
_VALID_ACTIONS = {
    "upload",
    "upload_text",
    "upload_b64",
    "list",
    "ls",
    "head",
    "exists",
    "get_text",
    "get_b64",
    "copy",
    "move",
    "url",
    "delete",
    "delete_prefix",
}


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
                        "Store content as objects in S3-style object storage. "
                        "Uses the provided key directly (no forced folder). "
                        "Supports upload/read/list/copy/move/delete operations."
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
                    "description": "Action: upload/upload_text/upload_b64/list/ls/head/exists/get_text/get_b64/copy/move/url/delete/delete_prefix",
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
                "prefix": {
                    "type": "string",
                    "description": "Prefix filter for ls/delete_prefix actions",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether ls should recurse directories (default: true)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows for ls (default: 200, max: 5000)",
                },
                "src_key": {
                    "type": "string",
                    "description": "Source key for copy/move actions",
                },
                "dst_key": {
                    "type": "string",
                    "description": "Destination key for copy/move actions",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Allow overwriting destination for copy/move (default: true)",
                },
                "encoding": {
                    "type": "string",
                    "description": "Text encoding for get_text action (default: utf-8)",
                },
                "errors": {
                    "type": "string",
                    "description": "Decode error mode for get_text: strict/ignore/replace",
                },
                "encrypt": {
                    "type": "boolean",
                    "description": "Encrypt object content (default: false)",
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
            "prefix": arguments.get("prefix"),
            "recursive": arguments.get("recursive"),
            "limit": arguments.get("limit"),
            "src_key": arguments.get("src_key"),
            "dst_key": arguments.get("dst_key"),
            "overwrite": arguments.get("overwrite"),
            "encoding": arguments.get("encoding"),
            "errors": arguments.get("errors"),
            "encrypt": arguments.get("encrypt", False),
        }
        request = json.dumps(payload, ensure_ascii=False)
        logger.info("hf_sync s3 action: user=%d action=%s", user_id, action)
        try:
            result = run_hf_sync_command(user_id, request)
            return str(result.get("output") or "")
        except Exception as exc:
            logger.exception("hf_sync s3 action failed: %s", action)
            return f"Error: action '{action}' failed - {exc}"
