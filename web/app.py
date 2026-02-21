"""FastAPI application factory."""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from web.routes.settings import router as settings_router
from web.routes.personas import router as personas_router
from web.routes.logs import router as logs_router
from web.routes.usage import router as usage_router
from web.routes.providers import router as providers_router
from web.routes.sessions import router as sessions_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Gemen Dashboard", docs_url=None, redoc_url=None)

    # API routers
    app.include_router(settings_router)
    app.include_router(personas_router)
    app.include_router(logs_router)
    app.include_router(usage_router)
    app.include_router(providers_router)
    app.include_router(sessions_router)

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

    @app.post("/api/auth/exchange")
    async def exchange_token(body: dict):
        """Exchange a short URL token for a JWT."""
        from web.auth import exchange_short_token
        short = body.get("token", "")
        jwt_token = exchange_short_token(short)
        return {"token": jwt_token}

    # Static files
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/")
        async def index():
            from fastapi.responses import FileResponse
            return FileResponse(os.path.join(static_dir, "index.html"))

    return app
