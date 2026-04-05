"""Route and static mounting for FastAPI app."""

import logging
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from web.live_logs import get_live_logs_text


def register_health_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})


def register_logs_routes(app: FastAPI) -> None:
    @app.get("/logs", include_in_schema=False)
    async def logs_page(lines: int = Query(default=500, ge=1, le=5000)):
        response = PlainTextResponse(get_live_logs_text(lines=lines))
        response.headers["Cache-Control"] = "no-store"
        return response


def register_auth_routes(app: FastAPI, logger: logging.Logger) -> None:
    @app.post("/api/auth/exchange")
    async def exchange_token(body: dict):
        from web.auth import exchange_short_token

        short = str(body.get("token", "")).strip()
        try:
            jwt_token = exchange_short_token(short)
            logger.info("web auth exchange success (token_len=%d)", len(short))
            return {"token": jwt_token}
        except HTTPException as exc:
            logger.warning("web auth exchange failed: %s (token_len=%d)", exc.detail, len(short))
            raise


def mount_static(app: FastAPI, logger: logging.Logger) -> None:
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    index_file = os.path.join(static_dir, "index.html")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    else:
        logger.warning("Static directory not found: %s", static_dir)

    @app.get("/")
    @app.get("/index.html")
    async def index():
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        logger.error("Dashboard index.html not found: %s", index_file)
        return JSONResponse(
            {
                "detail": "Dashboard static files not found on server",
                "expected_index": index_file,
            },
            status_code=500,
        )

