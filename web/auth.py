"""JWT authentication for the web dashboard."""

import threading
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import JWT_SECRET, JWT_EXPIRY_HOURS, JWT_SHORT_TOKEN_TTL_MINUTES

_security = HTTPBearer(auto_error=False)

# ── Legacy short token store ──
# Backward compatibility for old in-memory hex short tokens.
_short_tokens: dict[str, tuple[int, datetime]] = {}
_short_lock = threading.Lock()


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
    """Generate a signed short-lived token for web login.

    Uses a signed JWT short token so it works across multiple processes.
    Legacy in-memory tokens are still supported on exchange.
    """
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": int(user_id),
            "type": "short",
            "iat": now,
            "exp": now + timedelta(minutes=JWT_SHORT_TOKEN_TTL_MINUTES),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    # Prune legacy map opportunistically.
    with _short_lock:
        expired = [k for k, (_, exp) in _short_tokens.items() if exp < now]
        for k in expired:
            del _short_tokens[k]
    return token


def exchange_short_token(token: str) -> str:
    """Exchange a short token for a JWT.

    The short token is time-limited but can be exchanged more than once within
    TTL to tolerate link prefetch/preview behavior in chat apps.

    Returns a JWT string or raises HTTPException 401.
    """
    token = (token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # 1) Preferred path: signed short token (works across processes/instances).
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
        # Fall back to legacy in-memory map below.
        pass

    # 2) Legacy path: old hex token from in-memory map.
    with _short_lock:
        entry = _short_tokens.get(token)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id, expiry = entry
    if datetime.now(timezone.utc) > expiry:
        with _short_lock:
            _short_tokens.pop(token, None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    return create_jwt_token(user_id)


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
