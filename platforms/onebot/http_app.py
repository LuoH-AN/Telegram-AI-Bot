"""Combined FastAPI ASGI app: OneBot WebSocket + OpenAPI tool routes."""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from fastapi import FastAPI, WebSocket

from .ws_server import OneBotBridge

logger = logging.getLogger(__name__)


def build_onebot_app(runtime, *, ws_path: str = "/onebot/ws", mount_tools: bool = True) -> FastAPI:
    """Build the unified ASGI app hosting NapCat WS + OpenAPI tool routes."""
    app = FastAPI(
        title="Telegram-AI-Bot OneBot",
        version="1.0.0",
        description="NapCat WebSocket + OpenWebUI-compatible OpenAPI tools on a single port.",
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
            from openapi_tools.search_routes import router as search_router
            from openapi_tools.terminal_routes import router as terminal_router

            app.include_router(terminal_router, prefix="/tools")
            app.include_router(search_router, prefix="/tools")
            logger.info("Mounted OpenAPI tool routes under /tools (terminal + search)")
        except Exception:
            logger.exception("Failed to mount openapi_tools routers; OneBot WS still active")

    return app


async def serve_onebot_app(runtime, *, host: str, port: int, path: str = "/onebot/ws") -> None:
    """Run the combined FastAPI app under uvicorn until cancelled."""
    app = build_onebot_app(runtime, ws_path=path)
    config = uvicorn.Config(app, host=host, port=port, log_level="info", lifespan="on")
    server = uvicorn.Server(config)
    logger.info("OneBot+Tools server listening on http://%s:%d (ws %s, tools /tools/*)", host, port, path)
    try:
        await server.serve()
    except asyncio.CancelledError:
        server.should_exit = True
        raise
