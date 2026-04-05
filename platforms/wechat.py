"""WeChat AI Bot entry point using the official Weixin bot protocol."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from collections import OrderedDict
from cache import init_database
from config import (
    HEALTH_CHECK_PORT,
    SHOW_THINKING_MAX_CHARS,
    MAX_FILE_SIZE,
    MAX_TEXT_CONTENT_LENGTH,
)
from web.auth import create_short_token
from services.platform_shared import (
    apply_provider_command,
    build_provider_list_text,
    build_settings_text,
    build_usage_text,
    fetch_models_for_user,
    mask_key,
    normalize_reasoning_effort,
    normalize_stream_mode,
    start_web_server,
)
from services import (
    get_user_settings,
    update_user_setting,
    ensure_session,
    get_conversation,
    add_user_message,
    add_assistant_message,
    add_token_usage,
    has_api_key,
    get_system_prompt,
    get_remaining_tokens,
    get_current_persona_name,
    get_personas,
    switch_persona,
    create_persona,
    delete_persona,
    update_current_prompt,
    persona_exists,
    get_message_count,
    get_token_usage,
    export_to_markdown,
    set_token_limit,
    reset_token_usage,
    get_memories,
    add_memory,
    delete_memory,
    clear_memories,
    get_sessions,
    get_current_session,
    get_current_session_id,
    create_session,
    delete_chat_session,
    switch_session,
    rename_session,
    get_session_count,
    get_session_message_count,
    normalize_tts_endpoint,
    clear_conversation,
    generate_session_title,
    conversation_slot,
    handle_skill_command,
)
from services.cron import start_cron_scheduler, set_main_loop
from services.refresh import ensure_user_state
from services.runtime_queue import register_response, unregister_response, cancel_user_responses
from services.log import record_ai_interaction, record_error
from services.wechat_official import (
    DEFAULT_BOT_TYPE,
    WECHAT_TEXT_LIMIT,
    WeChatOfficialClient,
    local_chat_id_for_wechat,
)
from services.wechat_runtime import set_wechat_runtime
from ai import get_ai_client
from utils import (
    filter_thinking_content,
    extract_thinking_blocks,
    format_thinking_block,
    get_datetime_prompt,
    split_message,
    get_file_extension,
    is_text_file,
    is_image_file,
    is_likely_text,
    decode_file_content,
)
from utils.ai_helpers import (
    estimate_tokens as _estimate_tokens,
    estimate_tokens_str as _estimate_tokens_str,
)
from utils.platform_parity import (
    build_analyze_uploaded_files_message,
    build_api_key_required_message,
    build_api_key_verify_failed_message,
    build_api_key_verify_no_models_message,
    build_chat_commands_message,
    build_chat_no_sessions_message,
    build_chat_unknown_subcommand_message,
    build_endpoint_invalid_message,
    build_forget_usage_message,
    build_forget_invalid_target_message,
    build_global_prompt_help_message,
    build_help_message,
    build_invalid_memory_number_message,
    build_latex_guidance,
    build_memory_empty_message,
    build_memory_list_footer_message,
    build_persona_commands_message,
    build_persona_created_message,
    build_persona_new_usage_message,
    build_persona_not_found_message,
    build_persona_prompt_overview_message,
    build_prompt_per_persona_message,
    build_provider_save_hint_message,
    build_reasoning_effort_help_message,
    build_set_usage_message,
    build_show_thinking_help_message,
    build_start_message_missing_api,
    build_start_message_returning,
    build_stream_mode_help_message,
    build_token_limit_reached_message,
    build_unknown_set_key_message,
    build_usage_reset_message,
    build_remember_usage_message,
    build_retry_message,
    build_web_dashboard_message,
    format_log_context,
)
from handlers.messages.streaming import stream_response


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

WECHAT_COMMAND_PREFIX = os.getenv("WECHAT_COMMAND_PREFIX", "/").strip() or "/"
WECHAT_STATE_DIR = os.getenv("WECHAT_STATE_DIR", ".wechat_state").strip() or ".wechat_state"
WECHAT_ENABLED = str(os.getenv("WECHAT_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
WECHAT_BOT_TYPE = os.getenv("WECHAT_BOT_TYPE", DEFAULT_BOT_TYPE).strip() or DEFAULT_BOT_TYPE
WECHAT_LOGIN_ACCESS_TOKEN = os.getenv("WECHAT_LOGIN_ACCESS_TOKEN", "").strip()
WECHAT_GROUP_REPLY_ALL = str(os.getenv("WECHAT_GROUP_REPLY_ALL", "")).strip().lower() in {"1", "true", "yes", "on"}
WECHAT_GROUP_MENTION_ALIASES = [
    item.strip()
    for item in os.getenv(
        "WECHAT_GROUP_MENTION_ALIASES",
        "AI,ai,Bot,bot,助手,机器人,Gemen,gemen",
    ).split(",")
    if item.strip()
]
WECHAT_VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".mkv", ".avi")

def _wechat_ctx(local_user_id: int) -> str:
    return format_log_context(platform="wechat", user_id=local_user_id, scope="private", chat_id=local_user_id)


def _wechat_ctx_for_scope(*, local_user_id: int, local_chat_id: int, is_group: bool) -> str:
    return format_log_context(
        platform="wechat",
        user_id=local_user_id,
        scope="group" if is_group else "private",
        chat_id=local_chat_id,
    )

@dataclass
class WeChatMessageContext:
    runtime: "WeChatBotRuntime"
    peer_id: str
    reply_to_id: str
    local_user_id: int
    local_chat_id: int
    is_group: bool = False
    group_id: str | None = None
    context_token: str | None = None
    inbound_key: str | None = None

    @property
    def log_context(self) -> str:
        return _wechat_ctx_for_scope(
            local_user_id=self.local_user_id,
            local_chat_id=self.local_chat_id,
            is_group=self.is_group,
        )

    async def reply_text(self, text: str) -> None:
        await self.runtime.send_text_to_peer(
            self.reply_to_id,
            text,
            context_token=self.context_token,
            dedupe_key=self.inbound_key,
        )

    async def reply_file(self, file_path: str | Path, *, caption: str = "") -> None:
        await self.runtime.send_file_to_peer(
            self.reply_to_id,
            str(file_path),
            caption=caption,
            context_token=self.context_token,
            dedupe_key=self.inbound_key,
        )


class RecentKeyCache:
    """Small TTL cache for dedup / echo suppression."""

    def __init__(self, *, ttl_seconds: int, max_items: int):
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._lock = threading.RLock()
        self._items: OrderedDict[str, float] = OrderedDict()

    def _prune(self, now: float) -> None:
        expired = [key for key, ts in self._items.items() if now - ts > self._ttl_seconds]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)

    def seen(self, key: str | None) -> bool:
        if not key:
            return False
        now = time.time()
        with self._lock:
            self._prune(now)
            if key in self._items:
                self._items.move_to_end(key)
                return True
            return False

    def remember(self, key: str | None) -> None:
        if not key:
            return
        now = time.time()
        with self._lock:
            self._prune(now)
            self._items[key] = now
            self._items.move_to_end(key)

    def remember_once(self, key: str | None) -> bool:
        """Return True when key already exists, else remember it and return False."""
        if not key:
            return False
        now = time.time()
        with self._lock:
            self._prune(now)
            if key in self._items:
                self._items.move_to_end(key)
                return True
            self._items[key] = now
            self._items.move_to_end(key)
            return False


class NoopPump:
    """Minimal cancellation hook for runtime_queue registration."""

    def force_stop(self) -> None:
        return None


@dataclass(frozen=True)
class WeChatInboundEnvelope:
    message: dict
    inbound_key: str | None
    from_user_id: str
    to_user_id: str
    group_id: str | None
    reply_to_id: str
    text_body: str
    normalized_text: str
    item_types: tuple[int, ...]
    message_type: int
    message_state: int
    message_id: str
    seq: str

    @property
    def is_group(self) -> bool:
        return bool(self.group_id)

    @property
    def echo_target_id(self) -> str:
        return self.group_id or self.to_user_id or self.from_user_id


class WeChatBotRuntime:
    """Runtime wrapper so cron and commands can deliver WeChat messages."""

    def __init__(self) -> None:
        self.client = WeChatOfficialClient(state_dir=WECHAT_STATE_DIR, bot_type=WECHAT_BOT_TYPE)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._typing_lock = asyncio.Lock()
        self._seen_messages = RecentKeyCache(ttl_seconds=15 * 60, max_items=2048)
        self._sent_messages = RecentKeyCache(ttl_seconds=30, max_items=2048)
        self._recent_outbound_fingerprints = RecentKeyCache(ttl_seconds=60, max_items=2048)
        self.login_access_token = WECHAT_LOGIN_ACCESS_TOKEN or secrets.token_urlsafe(24)
        self._login_state_lock = threading.RLock()
        self._login_snapshot_path = Path(WECHAT_STATE_DIR) / "login_snapshot.json"
        self._active_qr: dict | None = None
        self._login_snapshot: dict = {
            "available": True,
            "logged_in": False,
            "status": "idle",
            "message": "WeChat runtime initialized",
            "user_id": "",
            "qr_url": "",
            "page_url": self._build_login_page_url(),
            "public_image_url": self._build_login_image_url(),
            "access_token_hint": self.login_access_token,
        }
        set_wechat_runtime(self)

    def _message_dedup_key(
        self,
        *,
        message_id: str,
        seq: str,
        create_time_ms: str,
        from_user_id: str,
        to_user_id: str,
        group_id: str | None,
        text_body: str,
    ) -> str | None:
        if message_id:
            return f"msgid:{message_id}"
        if seq and from_user_id:
            return f"seq:{seq}:from:{from_user_id}"
        if from_user_id and create_time_ms:
            body_hash = (
                hashlib.sha1(text_body.encode("utf-8")).hexdigest()[:16]
                if text_body
                else "no-body"
            )
            return f"fallback:{from_user_id}:{to_user_id}:{group_id}:{create_time_ms}:{body_hash}"
        return None

    def _outbound_fingerprint(self, *, target_id: str, text: str = "", item_types: tuple[int, ...] = ()) -> str:
        body = text.strip()
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:16] if body else "no-body"
        types = ",".join(str(item) for item in item_types) if item_types else "text"
        return f"{target_id}|{types}|{digest}"

    def _parse_inbound_message(self, message: dict) -> WeChatInboundEnvelope:
        from_user_id = str(message.get("from_user_id") or "").strip()
        to_user_id = str(message.get("to_user_id") or "").strip()
        group_id = str(message.get("group_id") or "").strip() or None
        text_body = _extract_text_body(message.get("item_list") or [])
        normalized_text = _strip_wechat_group_mentions(text_body) if group_id else text_body
        message_id = str(message.get("message_id") or "").strip()
        seq = str(message.get("seq") or "").strip()
        create_time_ms = str(message.get("create_time_ms") or "").strip()
        inbound_key = self._message_dedup_key(
            message_id=message_id,
            seq=seq,
            create_time_ms=create_time_ms,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            group_id=group_id,
            text_body=text_body,
        )
        return WeChatInboundEnvelope(
            message=message,
            inbound_key=inbound_key,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            group_id=group_id,
            reply_to_id=group_id or from_user_id,
            text_body=text_body,
            normalized_text=normalized_text,
            item_types=tuple(int(item.get("type") or 0) for item in (message.get("item_list") or [])),
            message_type=int(message.get("message_type") or 1),
            message_state=int(message.get("message_state") or 0),
            message_id=message_id,
            seq=seq,
        )

    def _should_skip_inbound_echo(self, inbound: WeChatInboundEnvelope, current_user_id: str) -> bool:
        if not current_user_id or not inbound.from_user_id or inbound.from_user_id != current_user_id:
            return False
        echo_fingerprint = self._outbound_fingerprint(
            target_id=inbound.echo_target_id,
            text=inbound.text_body,
            item_types=inbound.item_types or (1,),
        )
        if self._recent_outbound_fingerprints.seen(echo_fingerprint):
            logger.info(
                "Skipping outbound echo WeChat message: message_id=%s seq=%s state=%s from=%s fingerprint=%s",
                inbound.message_id,
                inbound.seq,
                inbound.message_state,
                inbound.from_user_id,
                echo_fingerprint,
            )
            return True
        logger.warning(
            "WeChat self-sent message did not match recent outbound fingerprint; processing continues: message_id=%s seq=%s state=%s from=%s fingerprint=%s",
            inbound.message_id,
            inbound.seq,
            inbound.message_state,
            inbound.from_user_id,
            echo_fingerprint,
        )
        return False

    def _build_login_page_url(self) -> str:
        from config import WEB_BASE_URL

        return f"{WEB_BASE_URL.rstrip('/')}/wechat/login?access={self.login_access_token}"

    def _build_login_image_url(self) -> str:
        from config import WEB_BASE_URL

        return f"{WEB_BASE_URL.rstrip('/')}/wechat/login/qr?access={self.login_access_token}"

    def _set_login_snapshot(self, **updates) -> dict:
        with self._login_state_lock:
            next_snapshot = dict(self._login_snapshot)
            next_snapshot.update(updates)
            next_snapshot["page_url"] = self._build_login_page_url()
            next_snapshot["public_image_url"] = self._build_login_image_url()
            self._login_snapshot = next_snapshot
            snapshot = dict(self._login_snapshot)
        try:
            self._login_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._login_snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Failed to persist WeChat login snapshot", exc_info=True)
        return snapshot

    def get_login_snapshot(self) -> dict:
        state = self.client.state_store.load()
        with self._login_state_lock:
            snapshot = dict(self._login_snapshot)
        if state.token:
            snapshot.update(
                {
                    "logged_in": True,
                    "status": "connected",
                    "message": "WeChat 已登录",
                    "user_id": state.user_id,
                    "qr_url": "",
                }
            )
        return snapshot

    def _start_login_session_sync(self, *, force: bool = False) -> dict:
        current = self.client.state_store.load()
        if force:
            current.token = ""
            current.user_id = ""
            current.get_updates_buf = ""
            current.peer_map = {}
            current.context_tokens = {}
            self.client.state_store.save(current)
        elif current.token:
            return self._set_login_snapshot(
                logged_in=True,
                status="connected",
                message="WeChat 已登录",
                user_id=current.user_id,
                qr_url="",
            )

        qr = self.client.fetch_qr_code()
        qrcode = str(qr.get("qrcode") or "").strip()
        qrcode_url = str(qr.get("qrcode_img_content") or "").strip()
        if not qrcode or not qrcode_url:
            raise RuntimeError(f"Failed to fetch WeChat QR code: {qr}")
        with self._login_state_lock:
            self._active_qr = {
                "qrcode": qrcode,
                "qr_url": qrcode_url,
                "started_at": time.time(),
                "status": "wait",
            }
        snapshot = self._set_login_snapshot(
            logged_in=False,
            status="wait",
            message="请打开页面链接或图片链接扫码登录",
            user_id="",
            qr_url=qrcode_url,
        )
        logger.info("WeChat login page: %s", snapshot["page_url"])
        logger.info("WeChat QR image link: %s", snapshot["public_image_url"])
        logger.info("WeChat upstream QR URL: %s", qrcode_url)
        return snapshot

    def force_new_login_sync(self) -> dict:
        with self._login_state_lock:
            self._active_qr = None
        return self._start_login_session_sync(force=True)

    async def login(self) -> None:
        state = self.client.state_store.load()
        if state.token:
            self._set_login_snapshot(
                logged_in=True,
                status="connected",
                message="WeChat 已登录",
                user_id=state.user_id,
                qr_url="",
            )
            return

        while True:
            with self._login_state_lock:
                active_qr = dict(self._active_qr) if self._active_qr else None
            if not active_qr:
                try:
                    await asyncio.to_thread(self._start_login_session_sync)
                except Exception:
                    logger.exception("Failed to start WeChat QR login session")
                    self._set_login_snapshot(
                        logged_in=False,
                        status="error",
                        message="二维码生成失败，请稍后重试",
                        user_id="",
                        qr_url="",
                    )
                    await asyncio.sleep(5)
                    continue
                with self._login_state_lock:
                    active_qr = dict(self._active_qr) if self._active_qr else None
                if not active_qr:
                    await asyncio.sleep(1)
                    continue

            status = await asyncio.to_thread(self.client.poll_qr_status, active_qr["qrcode"])
            status_value = str(status.get("status") or "wait")
            if status_value == "scaned":
                self._set_login_snapshot(
                    logged_in=False,
                    status="scaned",
                    message="已扫码，请在微信中确认授权",
                    user_id="",
                    qr_url=active_qr["qr_url"],
                )
            elif status_value == "confirmed" and status.get("bot_token"):
                current = self.client.state_store.load()
                current.token = str(status.get("bot_token") or "")
                current.user_id = str(status.get("ilink_user_id") or "")
                current.base_url = str(status.get("baseurl") or current.base_url or self.client.base_url)
                current.get_updates_buf = ""
                self.client.state_store.save(current)
                with self._login_state_lock:
                    self._active_qr = None
                self._set_login_snapshot(
                    logged_in=True,
                    status="connected",
                    message="WeChat 登录成功",
                    user_id=current.user_id,
                    qr_url="",
                )
                logger.info("WeChat login confirmed for user %s", current.user_id or "(unknown)")
                return
            elif status_value == "expired":
                logger.info("WeChat QR expired, refreshing login QR")
                try:
                    await asyncio.to_thread(self._start_login_session_sync, force=True)
                except Exception:
                    logger.exception("Failed to refresh WeChat QR login session")
                    self._set_login_snapshot(
                        logged_in=False,
                        status="error",
                        message="二维码刷新失败，请稍后重试",
                        user_id="",
                        qr_url="",
                    )
                    await asyncio.sleep(5)
                continue
            else:
                self._set_login_snapshot(
                    logged_in=False,
                    status="wait",
                    message="等待扫码中",
                    user_id="",
                    qr_url=active_qr["qr_url"],
                )
            await asyncio.sleep(2)

    async def safe_send_typing(self, peer_id: str, context_token: str | None, *, status: int) -> None:
        state = self.client.state_store.load()
        if not state.token:
            return
        try:
            config = await asyncio.to_thread(
                self.client.get_config,
                state.token,
                peer_id,
                context_token=context_token,
            )
            ticket = str(config.get("typing_ticket") or "").strip()
            if not ticket:
                return
            await asyncio.to_thread(
                self.client.send_typing,
                state.token,
                peer_id,
                ticket,
                status=status,
            )
        except Exception:
            logger.debug("Failed to update WeChat typing indicator", exc_info=True)

    async def send_text_to_peer(
        self,
        peer_id: str,
        text: str,
        *,
        context_token: str | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        state = self.client.state_store.load()
        if not state.token:
            raise RuntimeError("WeChat bot is not logged in")
        context = context_token or self.client.state_store.resolve_context_token(peer_id)
        chunks = split_message(text or "(Empty response)", max_length=WECHAT_TEXT_LIMIT)
        for index, chunk in enumerate(chunks or ["(Empty response)"]):
            outbound_key = f"text:{peer_id}:{dedupe_key}:{index}" if dedupe_key else None
            if self._sent_messages.remember_once(outbound_key):
                logger.info("Skipping duplicate WeChat outbound text: peer=%s dedupe_key=%s index=%s", peer_id, dedupe_key, index)
                continue
            logger.info("WeChat outbound text: peer=%s dedupe_key=%s index=%s len=%s", peer_id, dedupe_key, index, len(chunk))
            self._recent_outbound_fingerprints.remember(
                self._outbound_fingerprint(target_id=peer_id, text=chunk, item_types=(1,))
            )
            await asyncio.to_thread(
                self.client.send_text_message,
                state.token,
                peer_id,
                chunk,
                context_token=context,
            )

    async def send_file_to_peer(
        self,
        peer_id: str,
        file_path: str,
        *,
        caption: str = "",
        context_token: str | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        state = self.client.state_store.load()
        if not state.token:
            raise RuntimeError("WeChat bot is not logged in")
        context = context_token or self.client.state_store.resolve_context_token(peer_id)
        outbound_key = f"file:{peer_id}:{dedupe_key}:{file_path}:{caption}" if dedupe_key else None
        if self._sent_messages.remember_once(outbound_key):
            logger.info("Skipping duplicate WeChat outbound file: peer=%s dedupe_key=%s path=%s", peer_id, dedupe_key, file_path)
            return
        logger.info("WeChat outbound file: peer=%s dedupe_key=%s path=%s", peer_id, dedupe_key, file_path)
        media_type_code = _wechat_media_type_code_for_path(file_path)
        self._recent_outbound_fingerprints.remember(
            self._outbound_fingerprint(
                target_id=peer_id,
                text=caption or "",
                item_types=(media_type_code,),
            )
        )
        await asyncio.to_thread(
            self.client.send_media_file,
            state.token,
            peer_id,
            file_path,
            context_token=context,
            text=caption,
        )

    async def send_wechat_text(self, local_user_id: int, text: str) -> None:
        peer_id = self.client.state_store.resolve_peer(local_user_id)
        if not peer_id:
            raise RuntimeError(f"WeChat peer mapping not found for local user {local_user_id}")
        await self.send_text_to_peer(peer_id, text)

    async def _typing_loop(self, peer_id: str, context_token: str | None, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.safe_send_typing(peer_id, context_token, status=1)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=4)
            except asyncio.TimeoutError:
                continue
        await self.safe_send_typing(peer_id, context_token, status=2)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        set_main_loop(self._loop)
        start_cron_scheduler(self)

        while True:
            try:
                await self.login()
                state = self.client.state_store.load()
                response = await asyncio.to_thread(
                    self.client.get_updates,
                    state.token,
                    state.get_updates_buf,
                )
                if int(response.get("errcode") or 0) == -14:
                    logger.warning("WeChat session expired, clearing local token and restarting login")
                    self.client.state_store.clear_token()
                    await asyncio.sleep(2)
                    continue
                next_buf = str(response.get("get_updates_buf") or "")
                if next_buf:
                    state.get_updates_buf = next_buf
                    self.client.state_store.save(state)
                for message in response.get("msgs") or []:
                    await self.handle_message(message)
            except Exception:
                logger.exception("WeChat main loop failed")
                await asyncio.sleep(5)

    async def handle_message(self, message: dict) -> None:
        inbound = self._parse_inbound_message(message)
        if inbound.message_type == 2:
            return
        state = self.client.state_store.load()
        current_wechat_user_id = str(state.user_id or "").strip()
        if self._should_skip_inbound_echo(inbound, current_wechat_user_id):
            return
        if inbound.message_state == 1:
            logger.info("Skipping WeChat message with generating state")
            return
        if self._seen_messages.remember_once(inbound.inbound_key):
            logger.info(
                "Skipping duplicate WeChat message: inbound_key=%s message_id=%s seq=%s state=%s from=%s",
                inbound.inbound_key,
                inbound.message_id,
                inbound.seq,
                inbound.message_state,
                inbound.from_user_id,
            )
            return
        peer_id = inbound.from_user_id
        if not peer_id:
            return
        reply_to_id = inbound.reply_to_id
        local_chat_id = local_chat_id_for_wechat(reply_to_id)
        context_token = str(message.get("context_token") or "").strip() or None
        local_user_id = self.client.state_store.remember_peer(peer_id, context_token=context_token)
        if context_token:
            self.client.state_store.remember_context_token(reply_to_id, context_token)
        ctx = WeChatMessageContext(
            runtime=self,
            peer_id=peer_id,
            reply_to_id=reply_to_id,
            local_user_id=local_user_id,
            local_chat_id=local_chat_id,
            is_group=inbound.is_group,
            group_id=inbound.group_id,
            context_token=context_token,
            inbound_key=inbound.inbound_key,
        )
        logger.info(
            "%s inbound message (inbound_key=%s message_id=%s seq=%s state=%s group=%s)",
            ctx.log_context,
            inbound.inbound_key,
            inbound.message_id,
            inbound.seq,
            inbound.message_state,
            inbound.is_group,
        )

        if ctx.is_group and not _should_respond_in_wechat_group(inbound.text_body):
            return

        if inbound.normalized_text.startswith(WECHAT_COMMAND_PREFIX):
            await _dispatch_command(ctx, inbound.normalized_text)
            return

        await _process_chat_message(self, ctx, message)


def _extract_text_body(item_list: list[dict]) -> str:
    def _body_from_item(item: dict) -> str:
        item_type = int(item.get("type") or 0)
        if item_type == 1:
            text = str((item.get("text_item") or {}).get("text") or "").strip()
            ref_msg = item.get("ref_msg") or {}
            if not ref_msg:
                return text
            ref_item = ref_msg.get("message_item") or {}
            ref_item_type = int(ref_item.get("type") or 0)
            if ref_item_type in {2, 3, 4, 5}:
                return text
            parts: list[str] = []
            title = str(ref_msg.get("title") or "").strip()
            if title:
                parts.append(title)
            ref_text = _body_from_item(ref_item)
            if ref_text:
                parts.append(ref_text)
            if not parts:
                return text
            return f"[Quoted: {' | '.join(parts)}]\n{text}" if text else f"[Quoted: {' | '.join(parts)}]"
        if item_type == 3:
            return str((item.get("voice_item") or {}).get("text") or "").strip()
        return ""

    for item in item_list:
        text = _body_from_item(item)
        if text:
            return text
    return ""


def _strip_wechat_group_mentions(text: str) -> str:
    cleaned = text or ""
    for alias in WECHAT_GROUP_MENTION_ALIASES:
        cleaned = cleaned.replace(f"@{alias}", "")
        cleaned = cleaned.replace(f"＠{alias}", "")
    return cleaned.strip()


def _should_respond_in_wechat_group(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.startswith(WECHAT_COMMAND_PREFIX):
        return True
    if WECHAT_GROUP_REPLY_ALL:
        return True
    lowered = stripped.lower()
    for alias in WECHAT_GROUP_MENTION_ALIASES:
        alias_text = alias.strip()
        if not alias_text:
            continue
        alias_lower = alias_text.lower()
        if f"@{alias_lower}" in lowered or f"＠{alias_lower}" in lowered:
            return True
        if alias_lower in lowered and len(alias_lower) >= 3:
            return True
    return False


def _wechat_media_type_code_for_path(file_path: str) -> int:
    lower_path = file_path.lower()
    if is_image_file(file_path):
        return 2
    if lower_path.endswith(WECHAT_VIDEO_SUFFIXES):
        return 5
    return 4


async def _build_user_content_from_wechat_message(
    runtime: WeChatBotRuntime,
    message: dict,
    *,
    is_group: bool = False,
) -> tuple[str | list[dict], str]:
    item_list = list(message.get("item_list") or [])
    primary_text = _extract_text_body(item_list)
    if is_group:
        primary_text = _strip_wechat_group_mentions(primary_text)
    text_blocks: list[str] = []
    image_parts: list[dict] = []
    unsupported_files: list[str] = []
    oversized_files: list[str] = []
    file_names: list[str] = []

    for item in item_list:
        item_type = int(item.get("type") or 0)
        if item_type == 1:
            continue
        if item_type == 3:
            voice_text = str((item.get("voice_item") or {}).get("text") or "").strip()
            if not voice_text:
                unsupported_files.append("voice")
            continue
        if item_type not in {2, 4, 5}:
            continue

        try:
            downloaded = await asyncio.to_thread(
                runtime.client.download_media_to_path,
                item,
                Path(WECHAT_STATE_DIR) / "inbound",
            )
        except Exception:
            logger.debug("Failed to download WeChat attachment", exc_info=True)
            unsupported_files.append(f"attachment(type={item_type})")
            continue

        file_path = Path(str(downloaded["path"]))
        file_name = str(downloaded.get("filename") or file_path.name)
        file_names.append(file_name)

        if file_path.stat().st_size > MAX_FILE_SIZE:
            oversized_files.append(file_name)
            continue

        file_bytes = file_path.read_bytes()

        if item_type == 2 or is_image_file(file_name):
            import base64

            image_b64 = base64.b64encode(file_bytes).decode("utf-8")
            mime = str(downloaded.get("media_type") or "image/jpeg")
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                }
            )
            continue

        if is_text_file(file_name) or is_likely_text(file_bytes):
            file_content = decode_file_content(file_bytes)
            if file_content is None:
                unsupported_files.append(file_name)
                continue
            truncated = False
            if len(file_content) > MAX_TEXT_CONTENT_LENGTH:
                file_content = file_content[:MAX_TEXT_CONTENT_LENGTH]
                truncated = True
            label = f"[File: {file_name}]"
            if truncated:
                label += " (truncated)"
            text_blocks.append(f"{label}\n\n```\n{file_content}\n```")
            continue

        unsupported_files.append(file_name)

    if primary_text:
        text_blocks.insert(0, primary_text)

    text_prompt = "\n\n".join(part for part in text_blocks if part).strip()
    if oversized_files:
        text_prompt += (
            ("\n\n" if text_prompt else "")
            + "Skipped oversized files (max 20MB): "
            + ", ".join(oversized_files[:5])
            + (", ..." if len(oversized_files) > 5 else "")
        )
    if unsupported_files:
        text_prompt += (
            ("\n\n" if text_prompt else "")
            + "Skipped unsupported files: "
            + ", ".join(unsupported_files[:5])
            + (", ..." if len(unsupported_files) > 5 else "")
        )

    if image_parts:
        user_content: str | list[dict] = list(image_parts)
        if text_prompt:
            user_content.insert(0, {"type": "text", "text": text_prompt})
    else:
        user_content = text_prompt or build_analyze_uploaded_files_message()

    if len(file_names) == 1:
        save_msg = f"[File: {file_names[0]}]"
    elif file_names:
        preview = ", ".join(file_names[:3])
        if len(file_names) > 3:
            preview += ", ..."
        save_msg = f"[Files x{len(file_names)}] {preview}"
    else:
        save_msg = text_prompt or "[Message]"

    return user_content, save_msg


async def _process_chat_message(
    runtime: WeChatBotRuntime,
    ctx: WeChatMessageContext,
    message: dict,
) -> None:
    user_id = ctx.local_user_id
    ensure_user_state(user_id)

    user_content, save_msg = await _build_user_content_from_wechat_message(runtime, message, is_group=ctx.is_group)

    if isinstance(user_content, str) and not user_content.strip():
        await ctx.reply_text("Please send a text message or attachment.")
        return

    if not has_api_key(user_id):
        await ctx.reply_text(build_api_key_required_message(WECHAT_COMMAND_PREFIX))
        return

    persona_name = get_current_persona_name(user_id)
    remaining = get_remaining_tokens(user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await ctx.reply_text(build_token_limit_reached_message(WECHAT_COMMAND_PREFIX, persona_name))
        return

    settings = get_user_settings(user_id)
    user_reasoning_effort = _normalize_reasoning_effort(settings.get("reasoning_effort", ""))
    show_thinking = bool(settings.get("show_thinking"))
    session_id = ensure_session(user_id, persona_name)
    conversation = list(get_conversation(session_id))
    request_start = time.monotonic()

    request_token = ctx.inbound_key or message.get("message_id") or int(time.time() * 1000)
    slot_key = f"wechat:{ctx.local_chat_id}:{user_id}:{session_id}:{request_token}"
    slot_cm = conversation_slot(slot_key)
    was_queued = await slot_cm.__aenter__()
    final_delivery_confirmed = False
    current_task = asyncio.current_task()
    if current_task:
        register_response(slot_key, task=current_task, pump=NoopPump())

    typing_stop = asyncio.Event()
    typing_task = asyncio.create_task(runtime._typing_loop(ctx.reply_to_id, ctx.context_token, typing_stop))

    async def _noop_update(_text: str) -> bool:
        return True

    try:
        if was_queued:
            await ctx.reply_text("Previous request is still running. Queued and starting soon...")

        system_prompt = get_system_prompt(user_id, persona_name)
        system_prompt += "\n\n" + get_datetime_prompt()
        system_prompt += build_latex_guidance()

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append({"role": "user", "content": user_content})

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_thinking_seconds = 0
        truncated_prefix = ""
        last_text_response = ""
        thinking_segments: list[str] = []

        from tools import get_all_tools, process_tool_calls

        tool_definitions = get_all_tools(enabled_tools="all")

        while True:
            full_response, usage_info, thinking_seconds, finish_reason, reasoning_content, tool_calls = await stream_response(
                get_ai_client(user_id),
                messages,
                settings["model"],
                settings["temperature"],
                user_reasoning_effort,
                _noop_update,
                _noop_update,
                show_waiting=False,
                stream_mode="off",
                include_thought_prefix=False,
                stream_cursor=False,
                show_thinking=show_thinking,
                thinking_max_chars=SHOW_THINKING_MAX_CHARS,
                tools=tool_definitions,
            )
            total_thinking_seconds += thinking_seconds

            if show_thinking:
                tag_thinking, _ = extract_thinking_blocks(full_response)
                for segment in (reasoning_content, tag_thinking):
                    cleaned = (segment or "").strip()
                    if cleaned and (not thinking_segments or thinking_segments[-1] != cleaned):
                        thinking_segments.append(cleaned)

            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0

            if full_response.strip():
                last_text_response = full_response

            if tool_calls:
                tool_results = process_tool_calls(user_id, tool_calls, enabled_tools="all")
                messages.append(
                    {
                        "role": "assistant",
                        "content": full_response or "",
                        "tool_calls": [
                            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                            for tc in tool_calls
                        ],
                    }
                )
                for result in tool_results:
                    messages.append(result)
                continue

            if finish_reason == "length":
                truncated_text = full_response or ""
                truncated_prefix += truncated_text
                messages.append({"role": "assistant", "content": truncated_text})
                messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
                continue
            break

        combined_response = truncated_prefix + last_text_response if truncated_prefix else last_text_response
        final_text = filter_thinking_content(combined_response).strip()
        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response).strip()
        if not final_text:
            final_text = "(Empty response)"

        thinking_block = ""
        if show_thinking and thinking_segments:
            thinking_block = format_thinking_block(
                "\n\n".join(thinking_segments).strip(),
                seconds=total_thinking_seconds,
                max_chars=SHOW_THINKING_MAX_CHARS,
            )
        display_final = thinking_block + final_text if thinking_block else final_text

        await ctx.reply_text(display_final)
        final_delivery_confirmed = True
        add_user_message(session_id, save_msg)
        add_assistant_message(session_id, final_text)
        if get_session_message_count(session_id) <= 2:
            asyncio.create_task(_generate_and_set_title(user_id, session_id, save_msg, final_text))

        if not total_prompt_tokens and not total_completion_tokens:
            total_prompt_tokens = _estimate_tokens(messages)
            total_completion_tokens = _estimate_tokens_str(final_text)
        if total_prompt_tokens or total_completion_tokens:
            add_token_usage(user_id, total_prompt_tokens, total_completion_tokens, persona_name=persona_name)

        latency_ms = int((time.monotonic() - request_start) * 1000)
        record_ai_interaction(
            user_id,
            settings["model"],
            total_prompt_tokens,
            total_completion_tokens,
            total_prompt_tokens + total_completion_tokens,
            None,
            latency_ms,
            persona_name,
        )

    except asyncio.CancelledError:
        logger.info("%s response cancelled by /stop", ctx.log_context)
        if not final_delivery_confirmed:
            await ctx.reply_text("(Response stopped)")
    except Exception as exc:
        logger.exception("%s AI API error", ctx.log_context)
        if not final_delivery_confirmed:
            await ctx.reply_text(build_retry_message())
        record_error(user_id, str(exc), "wechat chat handler", settings.get("model"), persona_name)
    finally:
        typing_stop.set()
        try:
            await typing_task
        except Exception:
            pass
        unregister_response(slot_key)
        await slot_cm.__aexit__(None, None, None)


async def _generate_and_set_title(user_id: int, session_id: int, user_message: str, ai_response: str) -> None:
    try:
        from cache import cache

        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            logger.info("%s auto-generated session title: %s", _wechat_ctx(user_id), title)
    except Exception as exc:
        logger.warning("%s failed to auto-generate title: %s", _wechat_ctx(user_id), exc)


async def _dispatch_command(ctx: WeChatMessageContext, text: str) -> None:
    body = text[len(WECHAT_COMMAND_PREFIX):].strip()
    if not body:
        await ctx.reply_text(build_help_message(WECHAT_COMMAND_PREFIX))
        return
    name, _, rest = body.partition(" ")
    command = name.lower().strip()
    args = rest.split() if rest else []
    command_handlers = {
        "start": lambda: _start_command(ctx),
        "help": lambda: _help_command(ctx),
        "clear": lambda: _clear_command(ctx),
        "stop": lambda: _stop_command(ctx),
        "settings": lambda: _settings_command(ctx),
        "set": lambda: _set_command(ctx, *args),
        "usage": lambda: _usage_command(ctx, *args),
        "export": lambda: _export_command(ctx),
        "remember": lambda: _remember_command(ctx, content=rest or None),
        "memories": lambda: _memories_command(ctx),
        "forget": lambda: _forget_command(ctx, args[0] if args else None),
        "persona": lambda: _persona_command(ctx, *args),
        "chat": lambda: _chat_command(ctx, *args),
        "skill": lambda: _skill_command(ctx, *args),
        "web": lambda: _web_command(ctx),
    }
    handler = command_handlers.get(command)
    if handler is None:
        await ctx.reply_text(build_help_message(WECHAT_COMMAND_PREFIX))
        return
    await handler()


async def _start_command(ctx: WeChatMessageContext) -> None:
    user_id = ctx.local_user_id
    if not has_api_key(user_id):
        await ctx.reply_text(build_start_message_missing_api(WECHAT_COMMAND_PREFIX))
        return
    persona = get_current_persona_name(user_id)
    await ctx.reply_text(build_start_message_returning(persona, WECHAT_COMMAND_PREFIX))


async def _help_command(ctx: WeChatMessageContext) -> None:
    await ctx.reply_text(build_help_message(WECHAT_COMMAND_PREFIX))


async def _clear_command(ctx: WeChatMessageContext) -> None:
    user_id = ctx.local_user_id
    persona_name = get_current_persona_name(user_id)
    session_id = ensure_session(user_id, persona_name)
    clear_conversation(session_id)
    reset_token_usage(user_id)
    await ctx.reply_text(f"Conversation cleared and usage reset for persona '{persona_name}'.")


async def _stop_command(ctx: WeChatMessageContext) -> None:
    user_id = ctx.local_user_id
    cancelled = cancel_user_responses(ctx.local_chat_id, user_id, platform="wechat")
    if cancelled:
        await ctx.reply_text(f"Stopped {len(cancelled)} active response(s).")
    else:
        await ctx.reply_text("No active responses to stop.")


async def _settings_command(ctx: WeChatMessageContext) -> None:
    await ctx.reply_text(build_settings_text(ctx.local_user_id, command_prefix=WECHAT_COMMAND_PREFIX))


async def _set_command(ctx: WeChatMessageContext, *args: str) -> None:
    user_id = ctx.local_user_id
    settings = get_user_settings(user_id)
    p = WECHAT_COMMAND_PREFIX

    if not args:
        await ctx.reply_text(build_set_usage_message(p))
        return

    key = args[0].lower()
    if key == "model" and len(args) == 1:
        if not has_api_key(user_id):
            await ctx.reply_text(build_api_key_required_message(p))
            return
        models = await asyncio.get_running_loop().run_in_executor(None, lambda: fetch_models_for_user(user_id))
        if not models:
            await ctx.reply_text("Failed to fetch models. Check your API key and base_url.")
            return
        head = models[:40]
        extra = f"\n...and {len(models) - 40} more" if len(models) > 40 else ""
        await ctx.reply_text("Available models:\n" + "\n".join(head) + extra)
        return

    if len(args) < 2:
        if key == "provider":
            await _show_provider_list(ctx, settings)
            return
        if key == "stream_mode":
            await ctx.reply_text(build_stream_mode_help_message(p, settings.get("stream_mode", "") or "default"))
            return
        if key == "show_thinking":
            await ctx.reply_text(build_show_thinking_help_message(p, "on" if settings.get("show_thinking") else "off"))
            return
        if key == "reasoning_effort":
            await ctx.reply_text(build_reasoning_effort_help_message(p, settings.get("reasoning_effort", "") or "(provider/model default)"))
            return
        if key == "global_prompt":
            current = settings.get("global_prompt", "") or "(none)"
            display = current[:100] + "..." if len(current) > 100 else current
            await ctx.reply_text(build_global_prompt_help_message(p, display))
            return
        await ctx.reply_text(build_set_usage_message(p))
        return

    value = " ".join(args[1:]).strip()

    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        await ctx.reply_text(f"base_url set to: {value}")
        return
    if key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = _mask_key(value)
        try:
            models = await asyncio.get_running_loop().run_in_executor(None, lambda: fetch_models_for_user(user_id))
            if models:
                await ctx.reply_text(f"api_key set to: {masked}\nVerified ({len(models)} models available)")
            else:
                await ctx.reply_text(build_api_key_verify_no_models_message(masked))
        except Exception:
            await ctx.reply_text(build_api_key_verify_failed_message(masked))
        return
    if key == "model":
        update_user_setting(user_id, "model", value)
        await ctx.reply_text(f"model set to: {value}")
        return
    if key == "prompt":
        await ctx.reply_text(build_prompt_per_persona_message(p))
        return
    if key == "global_prompt":
        if not value or value.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "global_prompt", "")
            await ctx.reply_text("global_prompt cleared.\nNow personas will use their own system prompts only.")
            return
        update_user_setting(user_id, "global_prompt", value)
        display = value[:100] + "..." if len(value) > 100 else value
        await ctx.reply_text(
            f"global_prompt set to: {display}\n\nThis prompt will be prepended to all personas' system prompts.\nUse {p}set global_prompt clear to remove."
        )
        return
    if key == "temperature":
        try:
            temp = float(value)
        except ValueError:
            await ctx.reply_text("Invalid temperature value")
            return
        if not (0.0 <= temp <= 2.0):
            await ctx.reply_text("Temperature must be between 0.0 and 2.0")
            return
        update_user_setting(user_id, "temperature", temp)
        await ctx.reply_text(f"temperature set to: {temp}")
        return
    if key == "reasoning_effort":
        val = value.lower()
        if not val or val in {"off", "clear"}:
            update_user_setting(user_id, "reasoning_effort", "")
            await ctx.reply_text("reasoning_effort cleared (follow provider/model default).")
            return
        if val not in VALID_REASONING_EFFORTS:
            await ctx.reply_text("Invalid reasoning_effort. Available: none, minimal, low, medium, high, xhigh.")
            return
        update_user_setting(user_id, "reasoning_effort", val)
        await ctx.reply_text(f"reasoning_effort set to: {val}")
        return
    if key == "show_thinking":
        val = value.lower()
        if val in {"on", "true", "1", "yes", "y"}:
            update_user_setting(user_id, "show_thinking", True)
            await ctx.reply_text("show_thinking enabled.")
            return
        if val in {"off", "false", "0", "no", "n", "clear"}:
            update_user_setting(user_id, "show_thinking", False)
            await ctx.reply_text("show_thinking disabled.")
            return
        await ctx.reply_text(build_show_thinking_help_message(p, "on" if settings.get("show_thinking") else "off"))
        return
    if key == "token_limit":
        try:
            limit = int(value)
        except ValueError:
            await ctx.reply_text("Invalid token limit value")
            return
        if limit < 0:
            await ctx.reply_text("Token limit must be non-negative")
            return
        persona_name = get_current_persona_name(user_id)
        set_token_limit(user_id, limit, persona_name)
        await ctx.reply_text(f"Persona '{persona_name}' token_limit set to: {limit:,}" + (" (unlimited)" if limit == 0 else ""))
        return
    if key == "voice":
        update_user_setting(user_id, "tts_voice", value)
        await ctx.reply_text(f"voice set to: {value}")
        return
    if key == "style":
        update_user_setting(user_id, "tts_style", value.lower())
        await ctx.reply_text(f"style set to: {value.lower()}")
        return
    if key == "endpoint":
        if value.lower() in {"auto", "default", "off"}:
            update_user_setting(user_id, "tts_endpoint", "")
            await ctx.reply_text("endpoint set to: auto")
            return
        normalized = normalize_tts_endpoint(value)
        if not normalized:
            await ctx.reply_text(build_endpoint_invalid_message(p))
            return
        update_user_setting(user_id, "tts_endpoint", normalized)
        await ctx.reply_text(f"endpoint set to: {normalized}")
        return
    if key == "provider":
        await _handle_provider_command(ctx, user_id, settings, list(args[1:]))
        return
    if key == "title_model":
        if not value or value.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "title_model", "")
            await ctx.reply_text("title_model cleared (will use current provider + model)")
            return
        update_user_setting(user_id, "title_model", value)
        await ctx.reply_text(f"title_model set to: {value}")
        return
    if key == "cron_model":
        if not value or value.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "cron_model", "")
            await ctx.reply_text("cron_model cleared (will use current provider + model)")
            return
        update_user_setting(user_id, "cron_model", value)
        await ctx.reply_text(f"cron_model set to: {value}")
        return
    if key == "stream_mode":
        mode = value.lower()
        if mode in {"default", "time", "chars", "off"}:
            update_user_setting(user_id, "stream_mode", mode)
            await ctx.reply_text(f"stream_mode set to: {mode}")
            return
        if mode in {"", "clear", "none"}:
            update_user_setting(user_id, "stream_mode", "")
            await ctx.reply_text("stream_mode cleared (will use default mode)")
            return
        await ctx.reply_text(build_stream_mode_help_message(p, settings.get("stream_mode", "") or "default"))
        return
    await ctx.reply_text(build_unknown_set_key_message(key))


async def _show_provider_list(ctx: WeChatMessageContext, settings: dict) -> None:
    await ctx.reply_text(build_provider_list_text(settings, command_prefix=WECHAT_COMMAND_PREFIX))


async def _handle_provider_command(ctx: WeChatMessageContext, user_id: int, settings: dict, args: list[str]) -> None:
    await ctx.reply_text(
        apply_provider_command(
            user_id,
            settings,
            args,
            command_prefix=WECHAT_COMMAND_PREFIX,
        )
    )


async def _usage_command(ctx: WeChatMessageContext, *args: str) -> None:
    user_id = ctx.local_user_id
    persona_name = get_current_persona_name(user_id)
    if args and args[0].lower() == "reset":
        reset_token_usage(user_id, persona_name)
        await ctx.reply_text(build_usage_reset_message(persona_name))
        return
    await ctx.reply_text(build_usage_text(user_id))


async def _export_command(ctx: WeChatMessageContext) -> None:
    user_id = ctx.local_user_id
    persona_name = get_current_persona_name(user_id)
    file_buffer = export_to_markdown(user_id, persona_name)
    if file_buffer is None:
        await ctx.reply_text(f"No conversation history to export in current session (persona: '{persona_name}').")
        return
    export_dir = Path(WECHAT_STATE_DIR) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = getattr(file_buffer, "name", None) or f"chat_export_{persona_name}.md"
    path = export_dir / filename
    path.write_bytes(file_buffer.getvalue())
    try:
        await ctx.reply_file(path, caption=f"Chat history export (Persona: {persona_name})")
    except Exception:
        await ctx.reply_text(path.read_text("utf-8"))


async def _remember_command(ctx: WeChatMessageContext, *, content: str | None = None) -> None:
    if not content:
        await ctx.reply_text(build_remember_usage_message(WECHAT_COMMAND_PREFIX))
        return
    add_memory(ctx.local_user_id, content, source="user")
    await ctx.reply_text(f"Remembered: {content}")


async def _memories_command(ctx: WeChatMessageContext) -> None:
    memories = get_memories(ctx.local_user_id)
    if not memories:
        await ctx.reply_text(build_memory_empty_message(WECHAT_COMMAND_PREFIX))
        return
    lines = ["Your memories:\n"]
    for i, mem in enumerate(memories, 1):
        source_tag = "[AI]" if mem["source"] == "ai" else "[user]"
        lines.append(f"{i}. {source_tag} {mem['content']}")
    lines.append(build_memory_list_footer_message(WECHAT_COMMAND_PREFIX))
    await ctx.reply_text("\n".join(lines))


async def _forget_command(ctx: WeChatMessageContext, target: str | None = None) -> None:
    user_id = ctx.local_user_id
    if not target:
        await ctx.reply_text(build_forget_usage_message(WECHAT_COMMAND_PREFIX))
        return
    if target.lower() == "all":
        count = clear_memories(user_id)
        await ctx.reply_text(f"Cleared {count} memories." if count > 0 else "No memories to clear.")
        return
    try:
        index = int(target)
    except ValueError:
        await ctx.reply_text(build_forget_invalid_target_message(WECHAT_COMMAND_PREFIX))
        return
    if delete_memory(user_id, index):
        await ctx.reply_text(f"Memory #{index} deleted.")
    else:
        await ctx.reply_text(build_invalid_memory_number_message(index, WECHAT_COMMAND_PREFIX))


async def _persona_command(ctx: WeChatMessageContext, *args: str) -> None:
    user_id = ctx.local_user_id
    p = WECHAT_COMMAND_PREFIX
    if not args:
        personas = get_personas(user_id)
        current = get_current_persona_name(user_id)
        if not personas:
            await ctx.reply_text("No personas found.")
            return
        lines = ["Your personas:\n"]
        for name, persona in personas.items():
            marker = "> " if name == current else "  "
            usage = get_token_usage(user_id, name)
            session_id = ensure_session(user_id, name)
            msg_count = get_message_count(session_id)
            session_ct = get_session_count(user_id, name)
            prompt_preview = persona["system_prompt"][:30]
            if len(persona["system_prompt"]) > 30:
                prompt_preview += "..."
            lines.append(f"{marker}{name}")
            lines.append(f"    {msg_count} msgs | {session_ct} sessions | {usage['total_tokens']:,} tokens")
            lines.append(f"    {prompt_preview}")
            lines.append("")
        lines.append(build_persona_commands_message(p))
        await ctx.reply_text("\n".join(lines))
        return
    subcmd = args[0].lower()
    if subcmd == "new":
        if len(args) < 2:
            await ctx.reply_text(build_persona_new_usage_message(p))
            return
        name = args[1]
        prompt = " ".join(args[2:]) if len(args) > 2 else None
        if create_persona(user_id, name, prompt):
            switch_persona(user_id, name)
            await ctx.reply_text(build_persona_created_message(name, p))
        else:
            await ctx.reply_text(f"Persona '{name}' already exists.")
        return
    if subcmd == "delete":
        if len(args) < 2:
            await ctx.reply_text(f"Usage: {p}persona delete <name>")
            return
        name = args[1]
        if name == "default":
            await ctx.reply_text("Cannot delete the default persona.")
            return
        if delete_persona(user_id, name):
            await ctx.reply_text(f"Deleted persona: {name}")
        else:
            await ctx.reply_text(f"Persona '{name}' not found.")
        return
    if subcmd == "prompt":
        if len(args) < 2:
            persona = get_current_persona(user_id)
            await ctx.reply_text(build_persona_prompt_overview_message(persona["name"], persona["system_prompt"], p))
            return
        prompt = " ".join(args[1:])
        update_current_prompt(user_id, prompt)
        name = get_current_persona_name(user_id)
        await ctx.reply_text(f"Updated prompt for '{name}'.")
        return
    name = args[0]
    if not persona_exists(user_id, name):
        await ctx.reply_text(build_persona_not_found_message(name, p))
        return
    switch_persona(user_id, name)
    persona = get_current_persona(user_id)
    usage = get_token_usage(user_id, name)
    session_id = ensure_session(user_id, name)
    msg_count = get_message_count(session_id)
    session_ct = get_session_count(user_id, name)
    current_session = get_current_session(user_id, name)
    session_title = (current_session.get("title") or "New Chat") if current_session else "New Chat"
    prompt_text = persona["system_prompt"]
    if len(prompt_text) > 100:
        prompt_text = prompt_text[:100] + "..."
    await ctx.reply_text(
        f"Switched to: {name}\n\nMessages: {msg_count}\nSessions: {session_ct}\nCurrent session: {session_title}\nTokens: {usage['total_tokens']:,}\n\nPrompt: {prompt_text}"
    )


async def _skill_command(ctx: WeChatMessageContext, *args: str) -> None:
    result = handle_skill_command(ctx.local_user_id, list(args), command_prefix=f"{WECHAT_COMMAND_PREFIX}skill")
    await ctx.reply_text(result)


async def _chat_command(ctx: WeChatMessageContext, *args: str) -> None:
    user_id = ctx.local_user_id
    persona_name = get_current_persona_name(user_id)
    p = WECHAT_COMMAND_PREFIX
    if not args:
        sessions = get_sessions(user_id, persona_name)
        current_id = get_current_session_id(user_id, persona_name)
        if not sessions:
            await ctx.reply_text(build_chat_no_sessions_message(persona_name, p))
            return
        lines = [f"Sessions (persona: {persona_name})\n"]
        for i, session in enumerate(sessions, 1):
            marker = "> " if session["id"] == current_id else "  "
            title = session.get("title") or "New Chat"
            msg_count = get_session_message_count(session["id"])
            lines.append(f"{marker}{i}. {title} ({msg_count} msgs)")
        lines.append("")
        lines.append(build_chat_commands_message(p))
        await ctx.reply_text("\n".join(lines))
        return
    subcmd = args[0].lower()
    if subcmd == "new":
        title = " ".join(args[1:]) if len(args) > 1 else None
        session = create_session(user_id, persona_name, title)
        display_title = title or "New Chat"
        await ctx.reply_text(f"Created new session: {display_title}\nSwitched to session #{len(get_sessions(user_id, persona_name))}")
        logger.info("%s /chat new (session_id=%s)", ctx.log_context, session["id"])
        return
    if subcmd == "rename":
        if len(args) < 2:
            await ctx.reply_text(f"Usage: {p}chat rename <title>")
            return
        title = " ".join(args[1:])
        if rename_session(user_id, title, persona_name):
            await ctx.reply_text(f"Session renamed to: {title}")
        else:
            await ctx.reply_text("No current session to rename.")
        return
    if subcmd == "delete":
        if len(args) < 2:
            await ctx.reply_text(f"Usage: {p}chat delete <number>")
            return
        try:
            index = int(args[1])
        except ValueError:
            await ctx.reply_text("Please provide a valid session number.")
            return
        sessions = get_sessions(user_id, persona_name)
        if index < 1 or index > len(sessions):
            await ctx.reply_text(f"Invalid session number. Valid range: 1-{len(sessions)}")
            return
        display_title = sessions[index - 1].get("title") or "New Chat"
        if delete_chat_session(user_id, index, persona_name):
            await ctx.reply_text(f"Deleted session: {display_title}")
        else:
            await ctx.reply_text("Failed to delete session.")
        return
    try:
        index = int(subcmd)
    except ValueError:
        await ctx.reply_text(build_chat_unknown_subcommand_message(p))
        return
    if switch_session(user_id, index, persona_name):
        sessions = get_sessions(user_id, persona_name)
        session = sessions[index - 1]
        display_title = session.get("title") or "New Chat"
        msg_count = get_session_message_count(session["id"])
        await ctx.reply_text(f"Switched to session #{index}: {display_title}\nMessages: {msg_count}")
    else:
        total = len(get_sessions(user_id, persona_name))
        await ctx.reply_text(f"Invalid session number. Valid range: 1-{total}")


async def _web_command(ctx: WeChatMessageContext) -> None:
    from config import WEB_BASE_URL

    token = create_short_token(ctx.local_user_id)
    url = f"{WEB_BASE_URL.rstrip('/')}/?token={token}#token={token}"
    await ctx.reply_text(build_web_dashboard_message(url))


def main() -> None:
    if not WECHAT_ENABLED:
        logger.error("WECHAT_ENABLED is not enabled")
        return

    init_database()

    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    logger.info("Starting WeChat bot...")
    runtime = WeChatBotRuntime()
    asyncio.run(runtime.run())


if __name__ == "__main__":
    main()
