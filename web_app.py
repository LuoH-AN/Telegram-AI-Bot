"""Public-facing FastAPI app for the HF Space (port 7860).

Hosts:
- ``GET /`` and ``GET /healthz`` for the HF Space health probe.
- ``/tools/terminal/*`` and ``/tools/search/*`` — each tool mounted as a
  separate FastAPI sub-app so OpenWebUI can import each as its own tool
  server with a distinct OpenAPI spec:
    /tools/terminal/openapi.json
    /tools/search/openapi.json
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
        description="HF Space public surface: health and OpenWebUI tool server.",
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

    try:
        from openapi_tools.search_routes import build_search_app
        from openapi_tools.terminal_routes import build_terminal_app
        app.mount("/tools/terminal", build_terminal_app())
        app.mount("/tools/search", build_search_app())
        logger.info("web_app: mounted /tools/terminal and /tools/search as separate sub-apps")
    except Exception:
        logger.exception("web_app: failed to mount /tools — public server still serves health")

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
