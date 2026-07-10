"""Bearer-token auth helper for OpenAPI tool server."""

from __future__ import annotations

import hmac
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False, description="Bearer token (matches OPENAPI_TOOLS_TOKEN env)")


def _expected_token() -> str:
    return (os.getenv("OPENAPI_TOOLS_TOKEN") or "").strip()


def cors_options() -> dict:
    raw = (os.getenv("OPENAPI_TOOLS_CORS_ORIGINS") or "").strip()
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if not origins:
        origins = []
    return {
        "allow_origins": origins,
        "allow_credentials": bool(origins) and "*" not in origins,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    expected = _expected_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAPI_TOOLS_TOKEN is not configured",
        )
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    if not hmac.compare_digest((credentials.credentials or "").strip(), expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
