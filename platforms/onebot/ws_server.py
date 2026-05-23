"""OneBot bridge over a FastAPI/starlette WebSocket connection.

NapCat (or any OneBot v11 client) connects to ``ws://<host>:<port><path>`` as
a WebSocket client. ``OneBotBridge`` adapts that single inbound connection to
``runtime.handle_event`` and exposes ``_send_api`` for outbound calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class OneBotBridge:
    """Bridge between a single inbound NapCat WS connection and the runtime."""

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._connected = False
        self._send_lock = asyncio.Lock()
        self._echo_counter = 0
        self._pending: dict[str, asyncio.Future] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    async def serve_connection(self, websocket: WebSocket, runtime) -> None:
        if self._connected:
            logger.warning("Rejecting NapCat WS: another connection already active")
            await websocket.close(code=1013, reason="Bridge busy")
            return

        await websocket.accept()
        self._ws = websocket
        self._connected = True
        runtime._ws_bridge = self
        logger.info("NapCat WebSocket connected")

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from NapCat: %s", raw[:200])
                    continue
                await self._handle_message(msg, runtime)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("OneBot WS bridge error")
        finally:
            self._connected = False
            self._ws = None
            runtime._ws_bridge = None
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError("NapCat WebSocket disconnected"))
            self._pending.clear()
            logger.info("NapCat WebSocket disconnected")

    async def _handle_message(self, msg: dict, runtime) -> None:
        if msg.get("post_type") == "meta_event" and msg.get("meta_event_type") == "heartbeat":
            return

        if "echo" in msg:
            echo = str(msg["echo"])
            future = self._pending.pop(echo, None)
            if future and not future.done():
                if msg.get("status") == "failed":
                    future.set_exception(
                        RuntimeError(f"OneBot API error: {msg.get('retcode')}: {msg.get('data')}")
                    )
                else:
                    future.set_result(msg.get("data"))
            return

        try:
            await runtime.handle_event(msg)
        except Exception:
            logger.exception("OneBot event handler error")

    async def _send_api(self, action: str, params: dict | None = None) -> Any:
        if not self._connected or self._ws is None:
            raise RuntimeError("NapCat WebSocket is not connected")

        self._echo_counter += 1
        echo = f"{int(time.time() * 1000)}:{self._echo_counter}"
        payload: dict[str, Any] = {"action": action, "echo": echo}
        if params:
            payload["params"] = params

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[echo] = future

        async with self._send_lock:
            await self._ws.send_text(json.dumps(payload))

        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            raise TimeoutError(f"OneBot API call '{action}' timed out")
