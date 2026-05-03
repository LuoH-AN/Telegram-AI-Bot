"""Loopback HTTP login API for the WeChat runtime.

The Telegram process talks to WeChat through this thin REST layer because
they run as separate processes. Two routes are exposed on
``127.0.0.1:WECHAT_PORT``:

- ``GET  /api/wechat/login``      — return the current login snapshot
- ``POST /api/wechat/login/new``  — force a fresh QR-login session

Both routes require ``?access=<token>`` to match the runtime's
``login_access_token`` to avoid local-port abuse from other processes.
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from launcher import get_ports
from platforms.wechat.services.runtime import get_wechat_runtime

from ..config import logger


def _check_access(request: web.Request) -> tuple[bool, web.Response | None]:
    runtime = get_wechat_runtime()
    if runtime is None:
        return False, web.json_response({"detail": "WeChat runtime not registered"}, status=503)
    access = request.query.get("access", "")
    if not access or access != runtime.login_access_token:
        return False, web.json_response({"detail": "invalid access token"}, status=403)
    return True, None


async def _handle_get_snapshot(request: web.Request) -> web.Response:
    ok, err = _check_access(request)
    if not ok:
        return err
    runtime = get_wechat_runtime()
    snapshot = await asyncio.to_thread(runtime.get_login_snapshot)
    return web.json_response(snapshot)


async def _handle_force_new_login(request: web.Request) -> web.Response:
    ok, err = _check_access(request)
    if not ok:
        return err
    runtime = get_wechat_runtime()
    snapshot = await asyncio.to_thread(runtime.force_new_login_sync)
    return web.json_response(snapshot)


async def start_login_api_server() -> web.AppRunner:
    """Bind the loopback HTTP server. Caller owns the returned runner."""
    app = web.Application()
    app.router.add_get("/api/wechat/login", _handle_get_snapshot)
    app.router.add_post("/api/wechat/login/new", _handle_force_new_login)
    runner = web.AppRunner(app)
    await runner.setup()
    _, wechat_port, _ = get_ports()
    site = web.TCPSite(runner, "127.0.0.1", int(wechat_port))
    await site.start()
    logger.info("WeChat login API listening on 127.0.0.1:%s", wechat_port)
    return runner
