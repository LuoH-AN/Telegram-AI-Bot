"""Raw Telegram Bot API helpers for methods not yet wrapped by the SDK."""

from __future__ import annotations
import asyncio
import json
import logging
import urllib.error
import urllib.request
from infrastructure.config import TELEGRAM_API_BASE, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

def _api_url(method: str) -> str:
    base = TELEGRAM_API_BASE or "https://api.telegram.org"
    return f"{base}/bot{TELEGRAM_BOT_TOKEN}/{method}"

def _clean(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value is not None}

def _post_json(method: str, payload: dict, timeout: float) -> object | None:
    if not TELEGRAM_BOT_TOKEN:
        return None
    data = json.dumps(_clean(payload), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _api_url(method), data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.debug("Telegram Bot API %s failed: %s", method, detail)
        return None
    except Exception:
        logger.debug("Telegram Bot API %s failed", method, exc_info=True)
        return None
    if not body.get("ok"):
        logger.debug("Telegram Bot API %s returned: %s", method, body)
        return None
    return body.get("result")

async def call_bot_api(method: str, payload: dict, *, timeout: float = 10) -> object | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _post_json, method, payload, timeout)

async def send_message_draft(
    chat_id: int,
    draft_id: int,
    text: str,
    *,
    parse_mode: str = "HTML",
    message_thread_id: int | None = None,
) -> bool:
    return bool(await call_bot_api(
        "sendMessageDraft",
        {
            "chat_id": chat_id,
            "message_thread_id": message_thread_id,
            "draft_id": draft_id,
            "text": text,
            "parse_mode": parse_mode,
        },
    ))

async def send_rich_message_draft(
    chat_id: int,
    draft_id: int,
    rich_message: dict,
    *,
    message_thread_id: int | None = None,
) -> bool:
    return bool(await call_bot_api(
        "sendRichMessageDraft",
        {
            "chat_id": chat_id,
            "message_thread_id": message_thread_id,
            "draft_id": draft_id,
            "rich_message": rich_message,
        },
    ))

async def send_rich_message(
    chat_id: int,
    rich_message: dict,
    *,
    business_connection_id: str | None = None,
    direct_messages_topic_id: int | None = None,
    message_thread_id: int | None = None,
    reply_parameters: dict | None = None,
) -> object | None:
    return await call_bot_api(
        "sendRichMessage",
        {
            "business_connection_id": business_connection_id,
            "chat_id": chat_id,
            "direct_messages_topic_id": direct_messages_topic_id,
            "message_thread_id": message_thread_id,
            "rich_message": rich_message,
            "reply_parameters": reply_parameters,
        },
    )
