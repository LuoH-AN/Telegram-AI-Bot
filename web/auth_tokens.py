"""Token encode/decode helpers for dashboard auth."""

from datetime import datetime, timedelta, timezone

import jwt

from config import JWT_EXPIRY_HOURS, JWT_SECRET, JWT_SHORT_TOKEN_TTL_MINUTES


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def encode_jwt_token(user_id: int) -> str:
    now = _now_utc()
    payload = {
        "user_id": int(user_id),
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def encode_short_token(user_id: int) -> str:
    now = _now_utc()
    payload = {
        "user_id": int(user_id),
        "type": "short",
        "iat": now,
        "exp": now + timedelta(minutes=JWT_SHORT_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def encode_artifact_token(
    *,
    user_id: int,
    path: str,
    content_type: str = "application/octet-stream",
    filename: str = "",
    encrypted: bool = True,
    ttl_minutes: int = 60 * 24,
) -> str:
    now = _now_utc()
    payload = {
        "user_id": int(user_id),
        "type": "artifact",
        "path": str(path),
        "content_type": str(content_type or "application/octet-stream"),
        "filename": str(filename or ""),
        "encrypted": bool(encrypted),
        "iat": now,
        "exp": now + timedelta(minutes=max(1, int(ttl_minutes))),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

