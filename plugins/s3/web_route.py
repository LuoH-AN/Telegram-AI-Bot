"""HTTP handler for /s/{user_id}/{url_id} URLs."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _send_text(handler, status: int, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve_s3_url(handler, user_id: int, url_id: int) -> None:
    """Serve an S3 object identified by user_id and url_id."""
    try:
        from plugins.s3 import S3Service
        from plugins.s3.hf_backend import get_available_backend
        backend = get_available_backend()
        svc = S3Service(user_id, backend)
        svc.load()
        info = svc.get_object_by_url_id(url_id)
        if not info:
            _send_text(handler, 404, "Not Found")
            return
        result = svc.get_object(info["bucket"], info["key"])
        if not result.get("ok"):
            _send_text(handler, 404, "Not Found")
            return
        data = result.get("data", b"")
        ct = result.get("content_type") or "application/octet-stream"
        handler.send_response(200)
        handler.send_header("Content-Type", ct)
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
    except Exception as exc:
        logger.exception("serve_s3_url failed user=%d url_id=%d", user_id, url_id)
        _send_text(handler, 500, f"Error: {exc}")
