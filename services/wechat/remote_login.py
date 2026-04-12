"""Internal client for WeChat QR-login APIs."""

from __future__ import annotations

import asyncio

import aiohttp

from launcher import get_ports

from .login_access import get_wechat_login_access_token


def _base_url() -> str:
    _, _, wechat_port = get_ports()
    return f"http://127.0.0.1:{wechat_port}"


async def _request(method: str, path: str) -> dict:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.request(method, f"{_base_url()}{path}") as response:
                payload = await response.json(content_type=None)
        except Exception as exc:
            raise RuntimeError("WeChat runtime is not reachable. Start the WeChat process first.") from exc
    if response.status >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else ""
        raise RuntimeError(detail or f"WeChat login API failed with HTTP {response.status}")
    return payload if isinstance(payload, dict) else {}


async def get_wechat_login_snapshot() -> dict:
    access = get_wechat_login_access_token()
    return await _request("GET", f"/api/wechat/login?access={access}")


async def start_wechat_login(*, force: bool = False, wait_seconds: int = 15) -> dict:
    access = get_wechat_login_access_token()
    if force:
        snapshot = await _request("POST", f"/api/wechat/login/new?access={access}")
    else:
        snapshot = await get_wechat_login_snapshot()
        if not snapshot.get("logged_in") and not snapshot.get("qr_url"):
            snapshot = await _request("POST", f"/api/wechat/login/new?access={access}")
    for _ in range(max(0, wait_seconds)):
        if snapshot.get("logged_in") or snapshot.get("qr_url"):
            return snapshot
        await asyncio.sleep(1)
        snapshot = await get_wechat_login_snapshot()
    return snapshot
