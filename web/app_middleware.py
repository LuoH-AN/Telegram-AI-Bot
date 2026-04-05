"""FastAPI middleware installers."""

import logging

from fastapi import FastAPI, Request


def install_api_request_logger(app: FastAPI, logger: logging.Logger) -> None:
    @app.middleware("http")
    async def log_api_requests(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            return response

        user_id = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                from web.auth import verify_jwt_token

                user_id = verify_jwt_token(auth[7:])
            except Exception:
                user_id = None

        if user_id:
            logger.info("[user=%d] web %s %s → %d", user_id, request.method, path, response.status_code)
        else:
            logger.info("web %s %s → %d", request.method, path, response.status_code)
        return response

