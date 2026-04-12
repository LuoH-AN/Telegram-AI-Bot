"""FastAPI application factory."""

import logging

from fastapi import FastAPI

from web.routes.dashboard.settings import router as settings_router
from web.routes.dashboard.personas import router as personas_router
from web.routes.dashboard.logs import router as logs_router
from web.routes.dashboard.usage import router as usage_router
from web.routes.dashboard.providers import router as providers_router
from web.routes.dashboard.sessions import router as sessions_router
from web.routes.dashboard.cron import router as cron_router
from web.routes.dashboard.memories import router as memories_router
from web.routes.dashboard.models import router as models_router
from web.routes.integration.artifacts import router as artifacts_router
from web.routes.integration.deployments import router as deployments_router
from web.routes.integration.wechat import router as wechat_router
from web.live_logs import install_live_log_handler
from web.app_middleware import install_api_request_logger
from web.app_routes import mount_static, register_auth_routes, register_health_routes, register_logs_routes

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Gemen Dashboard", docs_url=None, redoc_url=None)
    install_live_log_handler()

    for router in (
        settings_router,
        personas_router,
        logs_router,
        usage_router,
        providers_router,
        sessions_router,
        cron_router,
        memories_router,
        models_router,
        artifacts_router,
        deployments_router,
        wechat_router,
    ):
        app.include_router(router)
    install_api_request_logger(app, logger)
    register_health_routes(app)
    register_logs_routes(app)
    register_auth_routes(app, logger)
    mount_static(app, logger)
    return app
