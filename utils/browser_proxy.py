"""Shared browser proxy helpers for Playwright/Crawl4AI tools."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

_SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
_SUPPORTED_PROXY_MODES = {"auto", "forward", "reverse", "off", "none", "disabled"}


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


def _resolve_proxy_mode() -> str:
    raw = _first_env("BROWSER_PROXY_MODE", "RESIN_PROXY_MODE") or "auto"
    mode = raw.strip().lower()
    if mode not in _SUPPORTED_PROXY_MODES:
        logger.warning("Unknown proxy mode '%s', falling back to auto", raw)
        return "auto"
    if mode in {"none", "disabled"}:
        return "off"
    return mode


def _has_resin_base_url() -> bool:
    return bool(_first_env("RESIN_PROXY_URL", "RESIN_PROXY_SERVER"))


def _should_use_reverse_proxy() -> bool:
    mode = _resolve_proxy_mode()
    if mode == "off":
        return False
    if mode == "reverse":
        return True
    if mode == "forward":
        return False
    # auto: prioritize Resin reverse mode when RESIN base is configured.
    if _has_resin_base_url():
        return True
    return False


def _build_reverse_platform_account(*, user_id: int | None) -> str:
    platform = _first_env("RESIN_PROXY_PLATFORM", "PROXY_PLATFORM")
    account_template = _first_env("RESIN_PROXY_ACCOUNT", "PROXY_ACCOUNT")
    account = _render_account(account_template, user_id)
    return f"{platform}:{account}"


def build_reverse_proxy_url(url: str, *, user_id: int | None = None) -> str | None:
    """Build Resin reverse-proxy URL for a target URL."""
    base_raw = _first_env("RESIN_PROXY_URL", "RESIN_PROXY_SERVER")
    if not base_raw:
        return None

    base = urlparse(base_raw if "://" in base_raw else f"http://{base_raw}")
    if not (base.scheme and base.netloc):
        logger.warning("Invalid RESIN proxy base URL: %s", base_raw)
        return None

    target = urlparse(url)
    target_scheme = (target.scheme or "").lower()
    if target_scheme not in {"http", "https"}:
        logger.warning("Unsupported target scheme for reverse proxy: %s", target.scheme)
        return None
    target_host = target.netloc
    if not target_host:
        logger.warning("Invalid target URL for reverse proxy: %s", url)
        return None

    token = _first_env("RESIN_PROXY_TOKEN", "PROXY_TOKEN")
    platform_account = _build_reverse_platform_account(user_id=user_id)
    target_path = target.path or "/"
    if target.query:
        target_path = f"{target_path}?{target.query}"

    base_path = (base.path or "").rstrip("/")
    token_segment = f"/{token}" if token else ""
    reverse_path = f"{base_path}{token_segment}/{platform_account}/{target_scheme}/{target_host}{target_path}"
    return urlunparse((base.scheme, base.netloc, reverse_path, "", "", ""))


def resolve_browser_navigation_url(url: str, *, user_id: int | None = None) -> tuple[str, str]:
    """Resolve navigation URL and routing mode for browser-based tools.

    Returns:
        (url_to_navigate, mode) where mode is "direct" or "reverse".
    """
    if not _should_use_reverse_proxy():
        return url, "direct"

    reverse_url = build_reverse_proxy_url(url, user_id=user_id)
    if not reverse_url:
        return url, "direct"
    return reverse_url, "reverse"


def resolve_browser_proxy(*, user_id: int | None = None) -> dict[str, str] | None:
    """Resolve Playwright/Crawl4AI proxy config from environment variables.

    Returns None when reverse routing is active.

    Forward-proxy source priority:
    1) `BROWSER_PROXY_URL` / `BROWSER_PROXY_SERVER` / `PROXY_URL`
    2) (compat) `RESIN_PROXY_URL` only when `BROWSER_PROXY_MODE=forward`
    3) Explicit auth `BROWSER_PROXY_USERNAME` + `BROWSER_PROXY_PASSWORD`
    4) Resin auth `RESIN_PROXY_TOKEN`, `RESIN_PROXY_PLATFORM`, `RESIN_PROXY_ACCOUNT`
    5) Credentials embedded in proxy URL
    """
    if _should_use_reverse_proxy():
        return None

    raw_proxy_url = _first_env("BROWSER_PROXY_URL", "BROWSER_PROXY_SERVER", "PROXY_URL")
    if not raw_proxy_url:
        # Compatibility: explicit forward mode can still reuse RESIN_PROXY_URL.
        if _resolve_proxy_mode() == "forward":
            raw_proxy_url = _first_env("RESIN_PROXY_URL", "RESIN_PROXY_SERVER")
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


def browser_route_label(*, url: str, user_id: int | None = None) -> str:
    """Human-friendly route label for logs."""
    routed_url, mode = resolve_browser_navigation_url(url, user_id=user_id)
    if mode == "reverse":
        return f"reverse:{routed_url}"
    proxy = resolve_browser_proxy(user_id=user_id)
    if proxy:
        return f"forward:{proxy_label(proxy)}"
    return "direct"
