"""OneBot WebSocket integration route."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def register_onebot_ws_routes(app: None) -> None:
    """Register OneBot WebSocket endpoint. Called by platforms.onebot.runtime.app."""
    pass
