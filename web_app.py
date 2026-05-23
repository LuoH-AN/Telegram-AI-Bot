"""Public-facing FastAPI app for the HF Space (port 7860).

Hosts:
- ``GET /`` and ``GET /healthz`` for the HF Space health probe.
- ``GET /s/{user_id}/{url_id}`` for direct S3 object download.
- ``/tools/*`` OpenWebUI-compatible OpenAPI tool routes (terminal + search).

The OpenWebUI tool URL is the Space's public HTTPS URL itself (e.g.
``https://<owner>-<space>.hf.space``). The OpenAPI spec lives at
``/openapi.json``.
"""

from __future__ import annotations

import logging
import threading

import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def build_public_app() -> FastAPI:
    app = FastAPI(
        title="Telegram-AI-Bot Public Web",
        version="1.0.0",
        description="HF Space public surface: health, S3 downloads, and OpenWebUI tool server.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    def _root() -> Response:
        return Response(content="OK", media_type="text/plain; charset=utf-8")

    @app.get("/healthz", tags=["meta"])
    def _healthz() -> dict:
        return {"ok": True}

    @app.get("/s/{user_id}/{url_id}", tags=["s3"], include_in_schema=False)
    def _s3_object(user_id: int, url_id: int) -> Response:
        from plugins.s3.web_route import fetch_s3_object
        fetched = fetch_s3_object(int(user_id), int(url_id))
        return Response(content=fetched.body, status_code=fetched.status, media_type=fetched.content_type)

    try:
        from openapi_tools.search_routes import router as search_router
        from openapi_tools.terminal_routes import router as terminal_router
        app.include_router(terminal_router, prefix="/tools")
        app.include_router(search_router, prefix="/tools")
        logger.info("web_app: mounted /tools (terminal + search)")
    except Exception:
        logger.exception("web_app: failed to mount /tools — public server still serves health/S3")

    return app


def serve_in_thread(port: int, *, host: str = "0.0.0.0") -> threading.Thread:
    """Start uvicorn in a background daemon thread without hijacking signals."""
    app = build_public_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info", lifespan="on")
    config.install_signal_handlers = False  # main.py owns SIGINT/SIGTERM
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="web-app", daemon=True)
    thread.start()
    return thread
