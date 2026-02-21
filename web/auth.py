"""JWT authentication for the web dashboard."""

import secrets
import threading
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import JWT_SECRET, JWT_EXPIRY_HOURS

_security = HTTPBearer(auto_error=False)

# ── Short token store ──
# Maps short hex token → (user_id, expiry_datetime)
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
    """Generate a short random hex token that maps to a user_id.

    The short token is valid for 10 minutes and single-use.
    """
    token = secrets.token_hex(16)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    with _short_lock:
        # Prune expired tokens
        now = datetime.now(timezone.utc)
        expired = [k for k, (_, exp) in _short_tokens.items() if exp < now]
        for k in expired:
            del _short_tokens[k]
        _short_tokens[token] = (user_id, expiry)
    return token


def exchange_short_token(token: str) -> str:
    """Exchange a short token for a JWT. Consumes the short token.

    Returns a JWT string or raises HTTPException 401.
    """
    with _short_lock:
        entry = _short_tokens.pop(token, None)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id, expiry = entry
    if datetime.now(timezone.utc) > expiry:
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
