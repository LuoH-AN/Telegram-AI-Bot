"""OneBot API client for NapCat WebSocket connection.

Implements the OneBot 11 standard API over WebSocket reverse connection.
NapCat acts as the server; this client connects to it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class OneBotClient:
    """WebSocket client for OneBot 11 protocol (NapCat).

    Connects to NapCat's WebSocket endpoint and handles:
    - API calls (send messages, etc.)
    - Event reception (incoming messages)
    """

    def __init__(
        self,
        ws_url: str,
        access_token: str = "",
        on_event: Callable[[dict], Any] | None = None,
    ):
        self.ws_url = ws_url
        self.access_token = access_token
        self.on_event = on_event
        self._ws: Any = None
        self._recv_task: asyncio.Task | None = None
        self._connected = False
        self._send_lock = asyncio.Lock()
        self._echo_counter = 0
        self._pending: dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        import websockets

        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        logger.info("Connecting to NapCat at %s", self.ws_url)
        self._ws = await websockets.connect(self.ws_url, additional_headers=headers)
        self._connected = True
        logger.info("Connected to NapCat")
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def disconnect(self) -> None:
        self._connected = False
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _recv_loop(self) -> None:
        """Receive and dispatch events from NapCat."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                    self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from NapCat: %s", raw[:200])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("NapCat receive loop error")
            if self._connected:
                self._connected = False
                raise

    def _handle_message(self, msg: dict) -> None:
        """Handle incoming WebSocket message (event or response)."""
        if msg.get("post_type") == "meta_event" and msg.get("meta_event_type") == "heartbeat":
            return

        if "echo" in msg:
            echo = str(msg["echo"])
            future = self._pending.pop(echo, None)
            if future and not future.done():
                if msg.get("status") == "failed":
                    future.set_exception(Exception(f"OneBot API error: {msg.get('retcode')}: {msg.get('data')}"))
                else:
                    future.set_result(msg.get("data"))
            return

        if msg.get("post_type") in ("message", "notice", "request"):
            if self.on_event:
                try:
                    self.on_event(msg)
                except Exception:
                    logger.exception("Event handler error")
        else:
            logger.debug("Unhandled NapCat message: %s", msg)

    async def _send_api(self, action: str, params: dict | None = None) -> Any:
        """Send an API call and wait for response."""
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
            await self._ws.send(json.dumps(payload))

        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            raise TimeoutError(f"OneBot API call '{action}' timed out")

    @property
    def connected(self) -> bool:
        return self._connected

    # ---- OneBot 11 API calls ----

    async def send_private_msg(self, user_id: int, message: str | list, auto_escape: bool = False) -> dict:
        return await self._send_api("send_private_msg", {"user_id": user_id, "message": message, "auto_escape": auto_escape})

    async def send_group_msg(self, group_id: int, message: str | list, auto_escape: bool = False) -> dict:
        return await self._send_api("send_group_msg", {"group_id": group_id, "message": message, "auto_escape": auto_escape})

    async def send_msg(self, message: str | list, *, user_id: int | None = None, group_id: int | None = None, auto_escape: bool = False) -> dict:
        if group_id:
            return await self.send_group_msg(group_id, message, auto_escape=auto_escape)
        if user_id:
            return await self.send_private_msg(user_id, message, auto_escape=auto_escape)
        raise ValueError("Either user_id or group_id must be provided")

    async def get_login_info(self) -> dict:
        return await self._send_api("get_login_info")

    async def get_group_member_info(self, group_id: int, user_id: int, no_cache: bool = False) -> dict:
        return await self._send_api("get_group_member_info", {"group_id": group_id, "user_id": user_id, "no_cache": no_cache})

    async def get_stranger_info(self, user_id: int, no_cache: bool = False) -> dict:
        return await self._send_api("get_stranger_info", {"user_id": user_id, "no_cache": no_cache})

    async def delete_msg(self, message_id: int) -> dict:
        return await self._send_api("delete_msg", {"message_id": message_id})

    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 0) -> dict:
        return await self._send_api("set_group_ban", {"group_id": group_id, "user_id": user_id, "duration": duration})

    async def set_group_kick(self, group_id: int, user_id: int, reject_add_request: bool = False) -> dict:
        return await self._send_api("set_group_kick", {"group_id": group_id, "user_id": user_id, "reject_add_request": reject_add_request})

    async def set_group_leave(self, group_id: int) -> dict:
        return await self._send_api("set_group_leave", {"group_id": group_id})
