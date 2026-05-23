"""FastAPI app factory for the OpenWebUI tool server."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .search_routes import router as search_router
from .terminal_routes import router as terminal_router


def _title() -> str:
    return (os.getenv("OPENAPI_TOOLS_TITLE") or "Telegram-AI-Bot Tools").strip() or "Telegram-AI-Bot Tools"


def _description() -> str:
    return (
        "Terminal command execution and integrated web search exposed as OpenAPI tools "
        "for OpenWebUI. Configure this URL under Settings → Tools."
    )


def _cors_origins() -> list[str]:
    raw = (os.getenv("OPENAPI_TOOLS_CORS_ORIGINS") or "*").strip()
    if raw == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_app() -> FastAPI:
    app = FastAPI(
        title=_title(),
        version="1.0.0",
        description=_description(),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"ok": True, "name": _title(), "docs": "/docs", "openapi": "/openapi.json"}

    @app.get("/healthz", tags=["meta"], summary="Health probe")
    def healthz() -> dict:
        return {"ok": True}

    app.include_router(terminal_router)
    app.include_router(search_router)
    return app


app = build_app()
