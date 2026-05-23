"""HTTP handler for /s/{user_id}/{url_id} URLs."""

from __future__ import annotations

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)


class S3Fetched(NamedTuple):
    status: int
    body: bytes
    content_type: str


def fetch_s3_object(user_id: int, url_id: int) -> S3Fetched:
    """Backend-agnostic S3 fetch used by both stdlib http.server and FastAPI."""
    try:
        from plugins.s3 import S3Service
        from plugins.s3.hf_backend import get_available_backend
        backend = get_available_backend()
        svc = S3Service(user_id, backend)
        svc.load()
        info = svc.get_object_by_url_id(url_id)
        if not info:
            return S3Fetched(404, b"Not Found", "text/plain; charset=utf-8")
        result = svc.get_object(info["bucket"], info["key"])
        if not result.get("ok"):
            return S3Fetched(404, b"Not Found", "text/plain; charset=utf-8")
        data = result.get("data", b"") or b""
        ct = result.get("content_type") or "application/octet-stream"
        return S3Fetched(200, data, ct)
    except Exception as exc:
        logger.exception("fetch_s3_object failed user=%d url_id=%d", user_id, url_id)
        return S3Fetched(500, f"Error: {exc}".encode("utf-8"), "text/plain; charset=utf-8")


def _send_text(handler, status: int, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve_s3_url(handler, user_id: int, url_id: int) -> None:
    """Serve an S3 object identified by user_id and url_id via BaseHTTPRequestHandler."""
    fetched = fetch_s3_object(user_id, url_id)
    handler.send_response(fetched.status)
    handler.send_header("Content-Type", fetched.content_type)
    handler.send_header("Content-Length", str(len(fetched.body)))
    handler.end_headers()
    handler.wfile.write(fetched.body)
