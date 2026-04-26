"""OneBot runtime facade class."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import traceback
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

# Monotonic counter to detect module reload
_RUNTIME_INIT_COUNT = 0


class OneBotRuntime(
    RuntimeIdentMixin,
    RuntimeSendTextMixin,
    RuntimeLoopMixin,
):
    def __init__(self) -> None:
        global onebot_runtime, _RUNTIME_INIT_COUNT
        _RUNTIME_INIT_COUNT += 1
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
        # === COMPREHENSIVE DIAGNOSTIC LOG ===
        self_mod = sys.modules.get("platforms.onebot.runtime.app")
        svc_mod = sys.modules.get("services.onebot.runtime")
        logger.info("=" * 60)
        logger.info("[DIAG-INIT] pid=%s thread=%s _RUNTIME_INIT_COUNT=%s",
                     os.getpid(), threading.current_thread().name, _RUNTIME_INIT_COUNT)
        logger.info("[DIAG-INIT] self id=%s", id(self))
        logger.info("[DIAG-INIT] platforms.onebot.runtime.app module id=%s, onebot_runtime attr=%r",
                     id(self_mod), getattr(self_mod, 'onebot_runtime', 'MISSING'))
        logger.info("[DIAG-INIT] services.onebot.runtime module id=%s, _runtime attr=%r",
                     id(svc_mod), getattr(svc_mod, '_runtime', 'MISSING') if svc_mod else 'NOT IN sys.modules')
        # Dump all onebot-related sys.modules entries
        for k in sorted(sys.modules):
            if 'onebot' in k.lower():
                logger.info("[DIAG-INIT] sys.modules[%s] = id=%s", k, id(sys.modules[k]))
        # Show call stack to understand who's importing
        logger.info("[DIAG-INIT] call stack:\n%s", "".join(traceback.format_stack()))
        logger.info("=" * 60)
