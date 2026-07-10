"""FastAPI app factory for the standalone OpenWebUI tool server.

The root app provides health + index; each tool is mounted as its own sub-app
so OpenWebUI can import them separately:
    /terminal/openapi.json   (terminal tool spec)
    /search/openapi.json     (search tool spec)
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import cors_options
from .search_routes import build_search_app
from .terminal_routes import build_terminal_app


def _title() -> str:
    return (os.getenv("OPENAPI_TOOLS_TITLE") or "Telegram-AI-Bot Tools").strip() or "Telegram-AI-Bot Tools"


def build_app() -> FastAPI:
    app = FastAPI(
        title=_title(),
        version="1.0.0",
        description=(
            "Index of separately-importable OpenWebUI tool servers. "
            "Add /terminal and /search as their own Tool Server URLs."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        **cors_options(),
    )

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "ok": True,
            "name": _title(),
            "tools": {
                "terminal": {"openapi": "/terminal/openapi.json", "docs": "/terminal/docs"},
                "search": {"openapi": "/search/openapi.json", "docs": "/search/docs"},
            },
        }

    @app.get("/healthz", tags=["meta"], summary="Health probe")
    def healthz() -> dict:
        return {"ok": True}

    app.mount("/terminal", build_terminal_app())
    app.mount("/search", build_search_app())
    return app


app = build_app()
