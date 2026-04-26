"""OneBot WebSocket endpoint integrated into FastAPI.

When ONEBOT_MODE=ws, NapCat connects to /onebot/ws on the main
web server (port 7864 for OneBot process). This route passes all
messages to the OneBotRuntime via the FastAPIOneBotBridge.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
import traceback
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class FastAPIOneBotBridge:
    """Bridge between FastAPI WebSocket and OneBotRuntime event handling."""

    def __init__(self):
        self._ws: Any = None
        self._connected = False
        self._send_lock = asyncio.Lock()
        self._echo_counter = 0
        self._pending: dict[str, asyncio.Future] = {}

    async def handle_websocket(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._connected = True
        logger.info("NapCat WebSocket connected via FastAPI bridge")

        try:
            from platforms.onebot.runtime.app import onebot_runtime
            if onebot_runtime is not None:
                onebot_runtime._ws_bridge = self

            async for raw in websocket.iter_text():
                try:
                    msg = json.loads(raw)
                    await self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from NapCat: %s", raw[:200])
        except Exception:
            logger.exception("NapCat WebSocket error")
        finally:
            self._connected = False
            self._ws = None
            from platforms.onebot.runtime.app import onebot_runtime
            if onebot_runtime is not None:
                onebot_runtime._ws_bridge = None
            logger.info("NapCat WebSocket disconnected")

    async def _handle_message(self, msg: dict) -> None:
        logger.info("OneBot bridge msg: post_type=%s echo=%s", msg.get("post_type"), "echo" in msg)
        if msg.get("post_type") == "meta_event" and msg.get("meta_event_type") == "heartbeat":
            logger.info("OneBot bridge: ignoring meta_event heartbeat")
            return

        if "echo" in msg:
            logger.info("OneBot bridge: handling API echo response")
            echo = str(msg["echo"])
            future = self._pending.pop(echo, None)
            if future and not future.done():
                if msg.get("status") == "failed":
                    future.set_exception(Exception(f"OneBot API error: {msg.get('retcode')}: {msg.get('data')}"))
                else:
                    future.set_result(msg.get("data"))
            return

        # === COMPREHENSIVE DIAGNOSTIC LOG ===
        logger.info("=" * 60)
        logger.info("[DIAG-BRIDGE] pid=%s thread=%s", os.getpid(), threading.current_thread().name)
        # Dump all onebot-related sys.modules entries with ids
        for k in sorted(sys.modules):
            if 'onebot' in k.lower():
                logger.info("[DIAG-BRIDGE] sys.modules[%s] = id=%s", k, id(sys.modules[k]))
        # Check platforms.onebot.runtime.app directly
        rt_mod = sys.modules.get("platforms.onebot.runtime.app")
        logger.info("[DIAG-BRIDGE] platforms.onebot.runtime.app in sys.modules: %s, id=%s, onebot_runtime=%r",
                     rt_mod is not None, id(rt_mod) if rt_mod else "N/A",
                     getattr(rt_mod, 'onebot_runtime', 'MISSING') if rt_mod else "N/A")
        # Check services.onebot.runtime directly
        svc_mod = sys.modules.get("services.onebot.runtime")
        logger.info("[DIAG-BRIDGE] services.onebot.runtime in sys.modules: %s, id=%s, _runtime=%r",
                     svc_mod is not None, id(svc_mod) if svc_mod else "N/A",
                     getattr(svc_mod, '_runtime', 'MISSING') if svc_mod else "N/A")
        # Check _RUNTIME_INIT_COUNT to see if __init__ was ever called
        if rt_mod:
            logger.info("[DIAG-BRIDGE] _RUNTIME_INIT_COUNT=%s", getattr(rt_mod, '_RUNTIME_INIT_COUNT', 'MISSING'))
        # Now do the actual import and compare
        from platforms.onebot.runtime.app import onebot_runtime
        logger.info("[DIAG-BRIDGE] after import: onebot_runtime=%r, module id=%s (==sys.modules? %s)",
                     onebot_runtime, id(sys.modules["platforms.onebot.runtime.app"]),
                     id(sys.modules["platforms.onebot.runtime.app"]) == id(rt_mod) if rt_mod else "N/A")
        # Fallback
        from services.onebot.runtime import get_onebot_runtime
        fallback = get_onebot_runtime()
        logger.info("[DIAG-BRIDGE] get_onebot_runtime()=%r", fallback)
        # Call stack
        logger.info("[DIAG-BRIDGE] call stack:\n%s", "".join(traceback.format_stack()))
        logger.info("=" * 60)
        # === END DIAGNOSTIC ===

        if onebot_runtime is None:
            onebot_runtime = fallback
        if onebot_runtime is None:
            logger.warning("Bridge: onebot_runtime is None, cannot handle event")
            return
        if not hasattr(onebot_runtime, "handle_event"):
            logger.warning("Bridge: onebot_runtime has no handle_event method")
            return
        try:
            await onebot_runtime.handle_event(msg)
        except Exception:
            logger.exception("Event handler error")

    async def _send_api(self, action: str, params: dict | None = None) -> Any:
        if not self._connected or not self._ws:
            raise RuntimeError("Not connected to NapCat")

        self._echo_counter += 1
        echo = f"{int(time.time() * 1000)}:{self._echo_counter}"
        payload: dict[str, Any] = {"action": action, "echo": echo}
        if params:
            payload["params"] = params

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[echo] = future

        async with self._send_lock:
            await self._ws.send_text(json.dumps(payload))

        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            raise TimeoutError(f"OneBot API call '{action}' timed out")

    @property
    def connected(self) -> bool:
        return self._connected


# Module-level singleton
_bridge = FastAPIOneBotBridge()


@router.websocket("/onebot/ws")
async def onebot_websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await _bridge.handle_websocket(websocket)
    except WebSocketDisconnect:
        logger.info("NapCat WebSocket disconnected")
    except Exception:
        logger.exception("Error in OneBot WebSocket endpoint")
