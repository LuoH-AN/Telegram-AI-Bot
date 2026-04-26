"""OneBot runtime facade class."""

from __future__ import annotations

import asyncio
from pathlib import Path

from services.onebot.runtime import set_onebot_runtime

from ..config import (
    ONEBOT_ACCESS_TOKEN,
    ONEBOT_MODE,
    ONEBOT_SERVER_HOST,
    ONEBOT_SERVER_PORT,
    ONEBOT_WS_URL,
    QQ_COMMAND_PREFIX,
    QQ_STATE_DIR,
    logger,
)
from ..recent_cache import RecentKeyCache
from ..sdk import OneBotClient, OneBotServer

from .ident import RuntimeIdentMixin
from .loop import RuntimeLoopMixin
from .send_text import RuntimeSendTextMixin


# Module-level reference for FastAPI WS bridge
onebot_runtime: "OneBotRuntime | None" = None

# Global registry for bridge access (more reliable than module-level import)
_RUNTIME_REGISTRY: dict[str, "OneBotRuntime"] = {}


class OneBotRuntime(
    RuntimeIdentMixin,
    RuntimeSendTextMixin,
    RuntimeLoopMixin,
):
    def __init__(self) -> None:
        global onebot_runtime
        Path(QQ_STATE_DIR).mkdir(parents=True, exist_ok=True)
        self.command_prefix = QQ_COMMAND_PREFIX
        self._loop: asyncio.AbstractEventLoop | None = None
        self._seen_messages = RecentKeyCache(ttl_seconds=15 * 60, max_items=2048)
        self._sent_messages = RecentKeyCache(ttl_seconds=30, max_items=2048)
        self._recent_outbound_fingerprints = RecentKeyCache(ttl_seconds=60, max_items=2048)
        # Bridge for WS mode (FastAPI WebSocket endpoint)
        self._ws_bridge: Any = None

        if ONEBOT_MODE == "server":
            self.client: OneBotClient | OneBotServer = OneBotServer(
                ws_url=f"ws://{ONEBOT_SERVER_HOST}:{ONEBOT_SERVER_PORT}",
                access_token=ONEBOT_ACCESS_TOKEN,
            )
        elif ONEBOT_MODE == "ws":
            # In WS mode, the FastAPI app handles the WebSocket connection
            # The _ws_bridge will be set by the FastAPI route handler
            class _WsModeClient:
                connected = False
                on_event = None
                async def connect(self): pass
                async def close(self): pass
            self.client = _WsModeClient()
        else:
            self.client = OneBotClient(
                ws_url=ONEBOT_WS_URL,
                access_token=ONEBOT_ACCESS_TOKEN,
            )
        set_onebot_runtime(self)
        onebot_runtime = self
        _RUNTIME_REGISTRY["onebot"] = self