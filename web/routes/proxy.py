"""Reverse proxy for internal services started via shell tool.

When AI starts a web service inside the container (e.g. Flask, Gradio,
Streamlit), it listens on 127.0.0.1:<port> which is unreachable from outside.
This route forwards ``/proxy/<port>/...`` to the internal service so users
can access it through the existing WEB_BASE_URL.
"""

import asyncio
import logging

import requests as _requests
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxy"])

_TARGET_HOST = "127.0.0.1"
_MIN_PORT = 1024
_MAX_PORT = 65535
_PROXY_TIMEOUT = 60


def _self_port() -> int:
    from config.settings import HEALTH_CHECK_PORT
    return HEALTH_CHECK_PORT


# ── HTTP proxy ────────────────────────────────────────────────────

@router.api_route(
    "/proxy/{port}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_http(port: int, path: str, request: Request):
    if port < _MIN_PORT or port > _MAX_PORT:
        return Response(
            content=f"Port must be {_MIN_PORT}-{_MAX_PORT}",
            status_code=400,
        )
    if port == _self_port():
        return Response(content="Cannot proxy to self", status_code=400)

    target = f"http://{_TARGET_HOST}:{port}/{path}"
    qs = str(request.query_params)
    if qs:
        target += f"?{qs}"

    # Forward headers, drop hop-by-hop
    fwd_headers: dict[str, str] = {}
    skip = {"host", "transfer-encoding", "connection", "keep-alive", "upgrade"}
    for k, v in request.headers.items():
        if k.lower() not in skip:
            fwd_headers[k] = v

    body = await request.body()

    def _do():
        return _requests.request(
            method=request.method,
            url=target,
            headers=fwd_headers,
            data=body or None,
            timeout=_PROXY_TIMEOUT,
            stream=True,
            allow_redirects=False,
        )

    try:
        resp = await asyncio.to_thread(_do)
    except _requests.ConnectionError:
        return Response(
            content="无法连接到内部服务，请确认服务是否已启动。",
            status_code=502,
        )
    except _requests.Timeout:
        return Response(content="内部服务响应超时。", status_code=504)
    except Exception as exc:
        logger.warning("proxy error port=%d path=%s: %s", port, path, exc)
        return Response(content="代理请求失败。", status_code=502)

    # Build response, drop hop-by-hop headers
    drop = {"transfer-encoding", "connection", "keep-alive"}
    resp_headers: dict[str, str] = {}
    for k, v in resp.headers.items():
        if k.lower() not in drop:
            resp_headers[k] = v

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp_headers,
    )


# ── Convenience: /proxy/{port} without trailing slash ─────────────

@router.api_route(
    "/proxy/{port}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_http_root(port: int, request: Request):
    return await proxy_http(port, "", request)


# ── WebSocket proxy ──────────────────────────────────────────────

@router.websocket("/proxy/{port}/{path:path}/ws")
@router.websocket("/proxy/{port}/ws")
async def proxy_ws(port: int, websocket: WebSocket, path: str = ""):
    if port < _MIN_PORT or port > _MAX_PORT or port == _self_port():
        await websocket.close(code=4400)
        return

    import websockets  # type: ignore[import-untyped]

    target = f"ws://{_TARGET_HOST}:{port}/{path}"
    qs = str(websocket.query_params) if websocket.query_params else ""
    if qs:
        target += f"?{qs}"

    await websocket.accept()
    try:
        async with websockets.connect(target) as upstream:

            async def client_to_upstream():
                try:
                    while True:
                        data = await websocket.receive()
                        if "text" in data:
                            await upstream.send(data["text"])
                        elif "bytes" in data:
                            await upstream.send(data["bytes"])
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client():
                try:
                    async for msg in upstream:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except Exception:
                    pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except ImportError:
        await websocket.send_text("WebSocket proxy requires 'websockets' package.")
        await websocket.close(code=4500)
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
