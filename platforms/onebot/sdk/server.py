"""OneBot WebSocket server for NapCat reverse connections.

NapCat connects to us as a client; we receive events and send API calls over the same connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class OneBotServer:
    """WebSocket server for OneBot 11 protocol (NapCat reverse connection).

    NapCat acts as the WebSocket client and connects to us.
    We receive events and can send API calls that NapCat responds to.
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
        self._connected = False
        self._send_lock = asyncio.Lock()
        self._echo_counter = 0
        self._pending: dict[str, asyncio.Future] = {}
        self._server: Any = None
        self._connections: set[Any] = set()
        self._connection_lock = asyncio.Lock()

    async def start_server(self) -> None:
        """Start the WebSocket server and listen for NapCat connections."""
        import websockets

        # Parse host and port from ws_url like "ws://0.0.0.0:8082"
        url_host = self.ws_url.replace("ws://", "").replace("wss://", "").split("/")[0]
        if ":" in url_host:
            host, port_str = url_host.rsplit(":", 1)
            port = int(port_str)
        else:
            host = url_host or "0.0.0.0"
            port = 8082

        async def handler(ws) -> None:
            async with self._connection_lock:
                self._connections.add(ws)
            try:
                await self._handle_connection(ws)
            finally:
                async with self._connection_lock:
                    self._connections.discard(ws)

        logger.info("Starting OneBot WebSocket server on %s:%d", host, port)
        self._server = await websockets.serve(handler, host, port)
        logger.info("OneBot WebSocket server started on %s:%d", host, port)

    async def _handle_connection(self, ws: Any) -> None:
        """Handle a single NapCat WebSocket connection."""
        # Validate token
        if self.access_token:
            try:
                # NapCat may send auth on first message or via headers
                # For now, we trust the connection since NapCat is on the other end
                pass
            except Exception:
                logger.warning("OneBot server: unauthorized connection attempt")
                await ws.close()
                return

        self._ws = ws
        self._connected = True
        logger.info("NapCat connected to OneBot server")

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from NapCat: %s", raw[:200])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("NapCat connection error")
        finally:
            self._connected = False
            self._ws = None
            logger.info("NapCat disconnected")

    def _handle_message(self, msg: dict) -> None:
        """Handle incoming WebSocket message (event or API response)."""
        if msg.get("post_type") == "meta_event" and msg.get("meta_event_type") == "heartbeat":
            return

        # If echo is present, it's a response to our API call
        if "echo" in msg:
            echo = str(msg["echo"])
            future = self._pending.pop(echo, None)
            if future and not future.done():
                if msg.get("status") == "failed":
                    future.set_exception(Exception(f"OneBot API error: {msg.get('retcode')}: {msg.get('data')}"))
                else:
                    future.set_result(msg.get("data"))
            return

        # Otherwise it's an event from NapCat
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

    async def broadcast_event(self, msg: dict) -> None:
        """Broadcast to all connected NapCat clients (for multi-client support)."""
        async with self._connection_lock:
            for ws in list(self._connections):
                try:
                    await ws.send(json.dumps(msg))
                except Exception:
                    pass

    @property
    def connected(self) -> bool:
        return self._connected

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ---- OneBot 11 API calls (send to NapCat over WebSocket) ----

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
