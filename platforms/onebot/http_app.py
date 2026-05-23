"""Combined FastAPI ASGI app: OneBot WebSocket + optional OpenAPI tool routes."""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI, WebSocket

from .ws_server import OneBotBridge

logger = logging.getLogger(__name__)


def _default_mount_tools() -> bool:
    raw = (os.getenv("ONEBOT_MOUNT_TOOLS", "0") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on", "y"}


def build_onebot_app(runtime, *, ws_path: str = "/onebot/ws", mount_tools: bool | None = None) -> FastAPI:
    """Build the unified ASGI app hosting NapCat WS (+ optionally /tools/*).

    Tool routes default to OFF: in the HF Space deployment the public port is 7860
    served by main.py, and OneBot's 7864 is not externally reachable. Set
    ONEBOT_MOUNT_TOOLS=1 to expose tools on the OneBot port too.
    """
    if mount_tools is None:
        mount_tools = _default_mount_tools()

    app = FastAPI(
        title="Telegram-AI-Bot OneBot",
        version="1.0.0",
        description="NapCat WebSocket bridge for OneBot v11 reverse connections.",
    )
    bridge = OneBotBridge()

    @app.websocket(ws_path)
    async def _ws_endpoint(websocket: WebSocket) -> None:
        await bridge.serve_connection(websocket, runtime)

    @app.get("/healthz", tags=["meta"], include_in_schema=True)
    def _healthz() -> dict:
        return {"ok": True, "onebot_connected": bridge.connected}

    if mount_tools:
        try:
            from openapi_tools.search_routes import build_search_app
            from openapi_tools.terminal_routes import build_terminal_app

            app.mount("/tools/terminal", build_terminal_app())
            app.mount("/tools/search", build_search_app())
            logger.info("Mounted OpenAPI tool sub-apps under /tools/terminal and /tools/search")
        except Exception:
            logger.exception("Failed to mount openapi_tools sub-apps; OneBot WS still active")

    return app


async def serve_onebot_app(runtime, *, host: str, port: int, path: str = "/onebot/ws") -> None:
    """Run the OneBot FastAPI app under uvicorn until cancelled."""
    app = build_onebot_app(runtime, ws_path=path)
    config = uvicorn.Config(app, host=host, port=port, log_level="info", lifespan="on")
    server = uvicorn.Server(config)
    logger.info("OneBot server listening on http://%s:%d (ws %s)", host, port, path)
    try:
        await server.serve()
    except asyncio.CancelledError:
        server.should_exit = True
        raise
