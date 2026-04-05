"""JWT authentication for the web dashboard."""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from web.auth_tokens import (
    decode_token,
    encode_artifact_token,
    encode_jwt_token,
    encode_short_token,
)

_security = HTTPBearer(auto_error=False)


def create_jwt_token(user_id: int) -> str:
    return encode_jwt_token(user_id)


def create_short_token(user_id: int) -> str:
    return encode_short_token(user_id)


def create_artifact_token(
    *,
    user_id: int,
    path: str,
    content_type: str = "application/octet-stream",
    filename: str = "",
    encrypted: bool = True,
    ttl_minutes: int = 60 * 24,
) -> str:
    return encode_artifact_token(
        user_id=user_id,
        path=path,
        content_type=content_type,
        filename=filename,
        encrypted=encrypted,
        ttl_minutes=ttl_minutes,
    )


def exchange_short_token(token: str) -> str:
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        payload = decode_token(token)
        if payload.get("type") == "short":
            return create_jwt_token(int(payload["user_id"]))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def verify_jwt_token(token: str) -> int:
    try:
        payload = decode_token(token)
        return int(payload["user_id"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def verify_artifact_token(token: str) -> dict:
    try:
        payload = decode_token(token)
        if payload.get("type") != "artifact":
            raise ValueError("wrong token type")
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> int:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    return verify_jwt_token(credentials.credentials)
