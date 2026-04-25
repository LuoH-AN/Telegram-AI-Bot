"""Shared access token for internal WeChat login APIs."""

from __future__ import annotations

import hashlib
import os

from config import JWT_SECRET


def get_wechat_login_access_token() -> str:
    configured = str(os.getenv("WECHAT_LOGIN_ACCESS_TOKEN") or "").strip()
    if configured:
        return configured
    return hashlib.sha256(f"wechat-login:{JWT_SECRET}".encode("utf-8")).hexdigest()[:32]
