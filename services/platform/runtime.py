"""Shared runtime utilities for platform services."""

from __future__ import annotations

import logging
import os

import uvicorn

from ai import get_ai_client
from config import HEALTH_CHECK_PORT
from web.app import create_app

VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def start_web_server(logger: logging.Logger, *, port: int = HEALTH_CHECK_PORT) -> None:
    env_port = (os.getenv("PORT") or "").strip()
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            logger.warning("Invalid PORT value '%s'; fallback to %d", env_port, port)
    app = create_app()
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning", access_log=False)
    logger.info("Web server started on port %d", port)
    uvicorn.Server(config).run()


def mask_key(api_key: str) -> str:
    if not api_key:
        return "(empty)"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"


def normalize_stream_mode(mode: str | None) -> str:
    current = (mode or "").strip().lower()
    return current if current in {"default", "time", "chars", "off"} else "default"


def normalize_reasoning_effort(value: str | None) -> str:
    current = (value or "").strip().lower()
    return current if current in VALID_REASONING_EFFORTS else ""


def fetch_models_for_user(user_id: int) -> list[str]:
    try:
        return get_ai_client(user_id).list_models()
    except Exception:
        return []
