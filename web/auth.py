"""JWT authentication for the web dashboard."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import JWT_SECRET, JWT_EXPIRY_HOURS, JWT_SHORT_TOKEN_TTL_MINUTES

_security = HTTPBearer(auto_error=False)


def create_jwt_token(user_id: int) -> str:
    """Generate a JWT token for a given Telegram user ID."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def create_short_token(user_id: int) -> str:
    """Generate a signed short-lived token for web login."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "user_id": int(user_id),
            "type": "short",
            "iat": now,
            "exp": now + timedelta(minutes=JWT_SHORT_TOKEN_TTL_MINUTES),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def create_artifact_token(
    *,
    user_id: int,
    path: str,
    content_type: str = "application/octet-stream",
    filename: str = "",
    encrypted: bool = True,
    ttl_minutes: int = 60 * 24,
) -> str:
    """Generate a signed short-lived token for artifact viewing."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "user_id": int(user_id),
            "type": "artifact",
            "path": str(path),
            "content_type": str(content_type or "application/octet-stream"),
            "filename": str(filename or ""),
            "encrypted": bool(encrypted),
            "iat": now,
            "exp": now + timedelta(minutes=max(1, int(ttl_minutes))),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def exchange_short_token(token: str) -> str:
    """Exchange a short token for a JWT."""
    token = (token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") == "short":
            return create_jwt_token(int(payload["user_id"]))
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def verify_jwt_token(token: str) -> int:
    """Verify a JWT token and return the user_id.

    Raises HTTPException 401 on failure.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return int(payload["user_id"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def verify_artifact_token(token: str) -> dict:
    """Verify an artifact token and return the decoded payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "artifact":
            raise ValueError("wrong token type")
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> int:
    """FastAPI dependency: extract user_id from Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    return verify_jwt_token(credentials.credentials)
