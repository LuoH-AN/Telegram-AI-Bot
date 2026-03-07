"""FastAPI application factory."""

import logging
import os

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from web.routes.settings import router as settings_router
from web.routes.personas import router as personas_router
from web.routes.logs import router as logs_router
from web.routes.usage import router as usage_router
from web.routes.providers import router as providers_router
from web.routes.sessions import router as sessions_router
from web.routes.cron import router as cron_router
from web.routes.memories import router as memories_router
from web.routes.models import router as models_router
from web.routes.backup import router as backup_router
from web.routes.browser_view import router as browser_view_router
from web.routes.proxy import router as proxy_router
from web.live_logs import get_live_logs_text, install_live_log_handler

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Gemen Dashboard", docs_url=None, redoc_url=None)
    install_live_log_handler()

    # API routers
    app.include_router(settings_router)
    app.include_router(personas_router)
    app.include_router(logs_router)
    app.include_router(usage_router)
    app.include_router(providers_router)
    app.include_router(sessions_router)
    app.include_router(cron_router)
    app.include_router(memories_router)
    app.include_router(models_router)
    app.include_router(backup_router)
    app.include_router(browser_view_router)
    app.include_router(proxy_router)

    # Log all /api/ requests with user context
    @app.middleware("http")
    async def log_api_requests(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/"):
            user_id = None
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                try:
                    from web.auth import verify_jwt_token
                    user_id = verify_jwt_token(auth[7:])
                except Exception:
                    pass
            if user_id:
                logger.info("[user=%d] web %s %s → %d", user_id, request.method, path, response.status_code)
            else:
                logger.info("web %s %s → %d", request.method, path, response.status_code)
        return response

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @app.get("/logs", include_in_schema=False)
    async def logs_page(lines: int = Query(default=500, ge=1, le=5000)):
        """Return latest process logs as plain text."""
        body = get_live_logs_text(lines=lines)
        response = PlainTextResponse(body)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/auth/exchange")
    async def exchange_token(body: dict):
        """Exchange a short URL token for a JWT."""
        from web.auth import exchange_short_token
        short = str(body.get("token", "")).strip()
        try:
            jwt_token = exchange_short_token(short)
            logger.info("web auth exchange success (token_len=%d)", len(short))
            return {"token": jwt_token}
        except HTTPException as exc:
            logger.warning("web auth exchange failed: %s (token_len=%d)", exc.detail, len(short))
            raise

    # Static files
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    index_file = os.path.join(static_dir, "index.html")

    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    else:
        logger.warning("Static directory not found: %s", static_dir)

    @app.get("/")
    @app.get("/index.html")
    async def index():
        from fastapi.responses import FileResponse

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

    # Mount MCP server (share same port with web dashboard).
    # Keep this near the end because the MCP app is mounted on "", which acts like a catch-all.
    try:
        from tools.mcp_server import mount_mcp_to_app
        mount_mcp_to_app(app)
    except Exception as e:
        logger.warning("Failed to mount MCP server: %s", e)

    return app
