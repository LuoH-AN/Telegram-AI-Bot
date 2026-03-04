"""Shared browser proxy helpers for Playwright/Crawl4AI tools."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _first_env(*names: str) -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return ""


def _normalize_proxy_server(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    raw_with_scheme = value if "://" in value else f"http://{value}"
    parsed = urlparse(raw_with_scheme)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _SUPPORTED_PROXY_SCHEMES:
        raise ValueError(
            f"unsupported scheme '{scheme}' (allowed: {', '.join(sorted(_SUPPORTED_PROXY_SCHEMES))})"
        )

    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("missing proxy host")

    server = f"{scheme}://{host}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    return server


def _extract_url_credentials(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    if not value:
        return "", ""
    parsed = urlparse(value if "://" in value else f"http://{value}")
    return parsed.username or "", parsed.password or ""


def _render_account(account_template: str, user_id: int | None) -> str:
    if not account_template:
        return ""
    if "{user_id}" in account_template and user_id is not None:
        return account_template.replace("{user_id}", str(int(user_id)))
    return account_template


def _build_resin_username(*, user_id: int | None) -> str:
    token = _first_env("RESIN_PROXY_TOKEN", "PROXY_TOKEN")
    platform = _first_env("RESIN_PROXY_PLATFORM", "PROXY_PLATFORM")
    account_template = _first_env("RESIN_PROXY_ACCOUNT", "PROXY_ACCOUNT")
    account = _render_account(account_template, user_id)
    if not (token or platform or account):
        return ""
    return f"{token}:{platform}:{account}"


def resolve_browser_proxy(*, user_id: int | None = None) -> dict[str, str] | None:
    """Resolve Playwright/Crawl4AI proxy config from environment variables.

    Priority:
    1) `BROWSER_PROXY_URL` / `BROWSER_PROXY_SERVER` / `RESIN_PROXY_URL`
    2) Explicit auth `BROWSER_PROXY_USERNAME` + `BROWSER_PROXY_PASSWORD`
    3) Resin auth `RESIN_PROXY_TOKEN`, `RESIN_PROXY_PLATFORM`, `RESIN_PROXY_ACCOUNT`
    4) Credentials embedded in proxy URL
    """
    raw_proxy_url = _first_env(
        "BROWSER_PROXY_URL",
        "BROWSER_PROXY_SERVER",
        "RESIN_PROXY_URL",
        "RESIN_PROXY_SERVER",
        "PROXY_URL",
    )
    if not raw_proxy_url:
        return None

    try:
        server = _normalize_proxy_server(raw_proxy_url)
    except ValueError as e:
        logger.warning("Ignoring invalid browser proxy config: %s", e)
        return None

    url_username, url_password = _extract_url_credentials(raw_proxy_url)
    username = _env("BROWSER_PROXY_USERNAME")
    password = _env("BROWSER_PROXY_PASSWORD")

    resin_username = _build_resin_username(user_id=user_id)
    resin_password = _first_env("RESIN_PROXY_PASSWORD", "PROXY_PASSWORD")

    if not username and resin_username:
        username = resin_username
    if not password and resin_password:
        password = resin_password

    if not username and url_username:
        username = url_username
    if not password and url_password:
        password = url_password

    # Resin forward proxy commonly uses username only ("token:platform:account")
    # with an empty password.
    if username and not password and resin_username and username == resin_username:
        password = ""

    proxy: dict[str, str] = {"server": server}
    if username:
        proxy["username"] = username
    if username and password is not None:
        proxy["password"] = password

    bypass = _env("BROWSER_PROXY_BYPASS")
    if bypass:
        proxy["bypass"] = bypass

    return proxy


def proxy_label(proxy: dict[str, str] | None) -> str:
    """Return a safe proxy label for logs without exposing credentials."""
    if not proxy:
        return "disabled"
    server = proxy.get("server") or "configured"
    if not proxy.get("username"):
        return f"{server} (no-auth)"
    return f"{server} (auth)"
