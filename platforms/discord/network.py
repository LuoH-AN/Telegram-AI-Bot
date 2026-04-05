"""Discord network/base-url override helpers."""
from __future__ import annotations
from urllib.parse import urlsplit
from discord import asset as discord_asset, gateway as discord_gateway, http as discord_http, invite as discord_invite
from yarl import URL
from .config import DISCORD_API_BASE, DISCORD_CDN_BASE, DISCORD_GATEWAY_BASE, DISCORD_INVITE_BASE, logger
_DISCORD_CDN_PROXY_BASE: str | None = None
_DISCORD_GATEWAY_PROXY_URL: str | None = None

def _normalize_http_base(value: str, *, name: str) -> str | None:
    base = (value or "").strip()
    if not base:
        return None
    if not base.startswith(("http://", "https://")):
        logger.warning("Ignoring %s=%s because it does not start with http:// or https://", name, base)
        return None
    return base.rstrip("/")


def _normalize_ws_base(value: str, *, name: str) -> URL | None:
    base = (value or "").strip()
    if not base:
        return None
    if not base.startswith(("ws://", "wss://")):
        logger.warning("Ignoring %s=%s because it does not start with ws:// or wss://", name, base)
        return None
    gateway_url = URL(base)
    if gateway_url.query:
        logger.warning("Ignoring query string in %s; configure it on proxy side", name)
        gateway_url = gateway_url.with_query(None)
    if gateway_url.fragment:
        logger.warning("Ignoring fragment in %s; fragments are not used in ws URLs", name)
        gateway_url = gateway_url.with_fragment("")
    return gateway_url if gateway_url.path else gateway_url.with_path("/")


def _join_base_with_path(base: str, path_with_query: str) -> str:
    return f"{base}{path_with_query if path_with_query.startswith('/') else '/' + path_with_query}"


def _rewrite_cdn_url_if_needed(url: str) -> str:
    if not _DISCORD_CDN_PROXY_BASE:
        return url
    parsed = urlsplit(url)
    if (parsed.hostname or "").lower() not in {"cdn.discordapp.com", "media.discordapp.net"}:
        return url
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return _join_base_with_path(_DISCORD_CDN_PROXY_BASE, path)


def _resolve_discord_api_route_base() -> str | None:
    base = _normalize_http_base(DISCORD_API_BASE, name="DISCORD_API_BASE")
    if not base:
        return None
    suffix = f"/api/v{discord_http.INTERNAL_API_VERSION}"
    if base.endswith(suffix):
        return base
    return f"{base}/v{discord_http.INTERNAL_API_VERSION}" if base.endswith("/api") else f"{base}{suffix}"


def _patch_discord_httpclient_methods() -> None:
    if getattr(discord_http.HTTPClient.get_from_cdn, "_gemen_patched", False):
        return
    old_cdn = discord_http.HTTPClient.get_from_cdn
    old_gateway = discord_http.HTTPClient.get_bot_gateway
    async def _patched_get_from_cdn(self: discord_http.HTTPClient, url: str) -> bytes:
        return await old_cdn(self, _rewrite_cdn_url_if_needed(url))
    async def _patched_get_bot_gateway(self: discord_http.HTTPClient):
        shards, url, limits = await old_gateway(self)
        return (shards, _DISCORD_GATEWAY_PROXY_URL, limits) if _DISCORD_GATEWAY_PROXY_URL else (shards, url, limits)
    setattr(_patched_get_from_cdn, "_gemen_patched", True)
    setattr(_patched_get_bot_gateway, "_gemen_patched", True)
    discord_http.HTTPClient.get_from_cdn = _patched_get_from_cdn
    discord_http.HTTPClient.get_bot_gateway = _patched_get_bot_gateway


def apply_discord_network_overrides() -> None:
    global _DISCORD_CDN_PROXY_BASE, _DISCORD_GATEWAY_PROXY_URL
    route_base = _resolve_discord_api_route_base()
    if route_base:
        discord_http.Route.BASE = route_base
        logger.info("Discord API base overridden to %s", route_base)
    gateway_base = _normalize_ws_base(DISCORD_GATEWAY_BASE, name="DISCORD_GATEWAY_BASE")
    if gateway_base:
        _DISCORD_GATEWAY_PROXY_URL = str(gateway_base)
        discord_gateway.DiscordWebSocket.DEFAULT_GATEWAY = gateway_base
        logger.info("Discord Gateway base overridden to %s", _DISCORD_GATEWAY_PROXY_URL)
    else:
        _DISCORD_GATEWAY_PROXY_URL = None
    _DISCORD_CDN_PROXY_BASE = _normalize_http_base(DISCORD_CDN_BASE, name="DISCORD_CDN_BASE")
    if _DISCORD_CDN_PROXY_BASE:
        discord_asset.Asset.BASE = _DISCORD_CDN_PROXY_BASE
        logger.info("Discord CDN base overridden to %s", _DISCORD_CDN_PROXY_BASE)
    invite_base = _normalize_http_base(DISCORD_INVITE_BASE, name="DISCORD_INVITE_BASE")
    if invite_base:
        discord_invite.Invite.BASE = invite_base
        logger.info("Discord invite base overridden to %s", invite_base)
    _patch_discord_httpclient_methods()
