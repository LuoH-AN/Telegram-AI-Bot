"""Bearer-token auth helper for OpenAPI tool server."""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False, description="Bearer token (matches OPENAPI_TOOLS_TOKEN env)")


def _expected_token() -> str:
    return (os.getenv("OPENAPI_TOOLS_TOKEN") or "").strip()


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    expected = _expected_token()
    if not expected:
        return
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    if (credentials.credentials or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
