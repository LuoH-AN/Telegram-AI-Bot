"""Official Weixin channel protocol helpers.

This module ports the core network protocol used by
`@tencent-weixin/openclaw-weixin` so the existing Python bot can integrate
with the same upstream Weixin service without embedding the OpenClaw runtime.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from database import get_connection, get_dict_cursor

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_BOT_TYPE = "3"
ILINK_APP_ID = "bot"
# Matches @tencent-weixin/openclaw-weixin 2.1.6 => 0x00020106
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (1 << 8) | 6)
WECHAT_TEXT_LIMIT = 4000
WECHAT_MEDIA_MAX_BYTES = 100 * 1024 * 1024

_EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".silk": "audio/silk",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

_MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/silk": ".silk",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/x-tar": ".tar",
    "application/gzip": ".gz",
    "text/plain": ".txt",
    "text/csv": ".csv",
}


def local_user_id_for_wechat(peer_id: str) -> int:
    """Map a Weixin peer id to a stable signed-63-bit integer."""
    digest = hashlib.sha256(f"wechat:{peer_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    return value or 1


def local_chat_id_for_wechat(scope_id: str) -> int:
    """Map a Weixin chat scope id (peer or group) to a stable signed-63-bit integer."""
    digest = hashlib.sha256(f"wechat-chat:{scope_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    return value or 1


def get_mime_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _EXTENSION_TO_MIME:
        return _EXTENSION_TO_MIME[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def get_extension_from_mime(mime_type: str) -> str:
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    return _MIME_TO_EXTENSION.get(mime, ".bin")


def _aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _aes_ecb_padded_size(size: int) -> int:
    return ((size + 16) // 16) * 16


def _parse_aes_key_base64(aes_key_base64: str) -> bytes:
    decoded = base64.b64decode(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        try:
            text = decoded.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("wechat aes_key decoded to unsupported payload") from exc
        if all(ch in "0123456789abcdefABCDEF" for ch in text):
            return bytes.fromhex(text)
    raise ValueError(f"wechat aes_key decoded to unsupported length: {len(decoded)}")


@dataclass
class WeChatAccountState:
    token: str = ""
    user_id: str = ""
    base_url: str = DEFAULT_BASE_URL
    get_updates_buf: str = ""
    peer_map: dict[str, str] = field(default_factory=dict)
    context_tokens: dict[str, str] = field(default_factory=dict)


class WeChatStateStore:
    """Persist login state and peer mappings to PostgreSQL."""

    def __init__(self, state_dir: str | Path, *, account_key: str = "default"):
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._account_key = (account_key or "default").strip() or "default"
        self._lock = threading.RLock()
        self._cached_state: WeChatAccountState | None = None

    @staticmethod
    def _clone_state(state: WeChatAccountState) -> WeChatAccountState:
        return WeChatAccountState(
            token=state.token,
            user_id=state.user_id,
            base_url=state.base_url,
            get_updates_buf=state.get_updates_buf,
            peer_map=dict(state.peer_map),
            context_tokens=dict(state.context_tokens),
        )

    @staticmethod
    def _coerce_map(value: object) -> dict[str, str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = {}
        elif isinstance(value, dict):
            parsed = value
        else:
            parsed = {}
        if not isinstance(parsed, dict):
            return {}
        return {
            str(k): str(v)
            for k, v in parsed.items()
            if str(k).strip() and str(v).strip()
        }

    def _load_from_db(self) -> WeChatAccountState:
        try:
            with get_connection() as conn:
                with get_dict_cursor(conn) as cur:
                    cur.execute(
                        """
                        SELECT token, user_id, base_url, get_updates_buf, peer_map, context_tokens
                        FROM wechat_runtime_state
                        WHERE account_key = %s
                        """,
                        (self._account_key,),
                    )
                    row = cur.fetchone()
        except Exception:
            logger.exception("Failed to load WeChat state from database")
            return WeChatAccountState()

        if not row:
            return WeChatAccountState()

        return WeChatAccountState(
            token=str(row.get("token") or ""),
            user_id=str(row.get("user_id") or ""),
            base_url=str(row.get("base_url") or DEFAULT_BASE_URL),
            get_updates_buf=str(row.get("get_updates_buf") or ""),
            peer_map=self._coerce_map(row.get("peer_map")),
            context_tokens=self._coerce_map(row.get("context_tokens")),
        )

    def load(self, *, force: bool = False) -> WeChatAccountState:
        with self._lock:
            if self._cached_state is None or force:
                self._cached_state = self._load_from_db()
            return self._clone_state(self._cached_state)

    def save(self, state: WeChatAccountState) -> None:
        with self._lock:
            self._cached_state = self._clone_state(state)
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO wechat_runtime_state
                                (account_key, token, user_id, base_url, get_updates_buf, peer_map, context_tokens, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (account_key) DO UPDATE SET
                                token = EXCLUDED.token,
                                user_id = EXCLUDED.user_id,
                                base_url = EXCLUDED.base_url,
                                get_updates_buf = EXCLUDED.get_updates_buf,
                                peer_map = EXCLUDED.peer_map,
                                context_tokens = EXCLUDED.context_tokens,
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            (
                                self._account_key,
                                state.token,
                                state.user_id,
                                state.base_url,
                                state.get_updates_buf,
                                json.dumps(state.peer_map, ensure_ascii=False),
                                json.dumps(state.context_tokens, ensure_ascii=False),
                            ),
                        )
                    conn.commit()
            except Exception:
                logger.exception("Failed to save WeChat state to database")

    def clear_token(self) -> None:
        state = self.load()
        state.token = ""
        state.user_id = ""
        state.get_updates_buf = ""
        self.save(state)

    def remember_peer(self, peer_id: str, *, context_token: str | None = None) -> int:
        state = self.load()
        local_id = local_user_id_for_wechat(peer_id)
        state.peer_map[str(local_id)] = peer_id
        if context_token:
            state.context_tokens[peer_id] = context_token
        self.save(state)
        return local_id

    def remember_context_token(self, scope_id: str, context_token: str) -> None:
        if not scope_id or not context_token:
            return
        state = self.load()
        state.context_tokens[scope_id] = context_token
        self.save(state)

    def resolve_peer(self, local_user_id: int) -> str | None:
        return self.load().peer_map.get(str(local_user_id))

    def resolve_context_token(self, peer_id: str) -> str | None:
        return self.load().context_tokens.get(peer_id)


class WeChatOfficialClient:
    """HTTP client for the official Weixin bot protocol."""

    def __init__(
        self,
        *,
        state_dir: str | Path,
        base_url: str = DEFAULT_BASE_URL,
        cdn_base_url: str = DEFAULT_CDN_BASE_URL,
        bot_type: str = DEFAULT_BOT_TYPE,
        account_key: str = "default",
    ):
        self.base_url = base_url.rstrip("/")
        self.cdn_base_url = cdn_base_url.rstrip("/")
        self.bot_type = bot_type
        self.state_store = WeChatStateStore(state_dir, account_key=account_key)
        self._session = requests.Session()

    def _random_wechat_uin(self) -> str:
        value = secrets.randbelow(2**32)
        return base64.b64encode(str(value).encode("utf-8")).decode("utf-8")

    def _common_headers(self) -> dict[str, str]:
        return {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        body: dict | None = None,
        token: str | None = None,
        timeout: float = 15,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
    ):
        url = endpoint if endpoint.startswith(("http://", "https://")) else urljoin((base_url or self.base_url).rstrip("/") + "/", endpoint.lstrip("/"))
        headers = self._common_headers()
        if method.upper() == "POST":
            headers["AuthorizationType"] = "ilink_bot_token"
            headers["X-WECHAT-UIN"] = self._random_wechat_uin()
            if token:
                headers["Authorization"] = f"Bearer {token.strip()}"
        if extra_headers:
            headers.update(extra_headers)
        data = None
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type or "application/octet-stream"
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        response = self._session.request(method=method.upper(), url=url, headers=headers, data=data, timeout=timeout)
        response.raise_for_status()
        return response

    def fetch_qr_code(self) -> dict:
        response = self._request(
            "GET",
            f"ilink/bot/get_bot_qrcode?bot_type={self.bot_type}",
            timeout=15,
        )
        return response.json()

    def poll_qr_status(self, qrcode: str, *, timeout_ms: int = 35_000) -> dict:
        try:
            response = self._request(
                "GET",
                f"ilink/bot/get_qrcode_status?qrcode={requests.utils.quote(qrcode, safe='')}",
                timeout=max(1.0, timeout_ms / 1000),
            )
            return response.json()
        except requests.Timeout:
            return {"status": "wait"}

    def get_updates(self, token: str, get_updates_buf: str, *, timeout_ms: int = 35_000) -> dict:
        try:
            response = self._request(
                "POST",
                "ilink/bot/getupdates",
                body={
                    "get_updates_buf": get_updates_buf or "",
                    "base_info": {"channel_version": "python-gemen-wechat"},
                },
                token=token,
                timeout=max(1.0, timeout_ms / 1000),
            )
            return response.json()
        except requests.Timeout:
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf or ""}

    def get_config(self, token: str, ilink_user_id: str, *, context_token: str | None = None) -> dict:
        response = self._request(
            "POST",
            "ilink/bot/getconfig",
            body={
                "ilink_user_id": ilink_user_id,
                "context_token": context_token or "",
            },
            token=token,
            timeout=10,
        )
        return response.json()

    def send_typing(self, token: str, ilink_user_id: str, typing_ticket: str, *, status: int) -> dict:
        response = self._request(
            "POST",
            "ilink/bot/sendtyping",
            body={
                "ilink_user_id": ilink_user_id,
                "typing_ticket": typing_ticket,
                "status": int(status),
            },
            token=token,
            timeout=10,
        )
        return response.json()

    def send_text_message(
        self,
        token: str,
        to_user_id: str,
        text: str,
        *,
        context_token: str | None = None,
    ) -> str:
        client_id = f"gemen-wechat-{uuid.uuid4().hex}"
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": 2,
                "message_state": 2,
                "item_list": [{"type": 1, "text_item": {"text": text}}],
                "context_token": context_token or None,
            }
        }
        self._request("POST", "ilink/bot/sendmessage", body=body, token=token, timeout=15)
        return client_id

    def _get_upload_url(self, token: str, payload: dict) -> dict:
        response = self._request(
            "POST",
            "ilink/bot/getuploadurl",
            body=payload,
            token=token,
            timeout=15,
        )
        return response.json()

    def _upload_ciphertext(
        self,
        plaintext: bytes,
        *,
        aes_key: bytes,
        upload_full_url: str | None,
        upload_param: str | None,
        filekey: str,
    ) -> str:
        ciphertext = _aes_ecb_encrypt(plaintext, aes_key)
        if upload_full_url:
            url = upload_full_url.strip()
        elif upload_param:
            url = f"{self.cdn_base_url}/upload?encrypted_query_param={requests.utils.quote(upload_param, safe='')}&filekey={requests.utils.quote(filekey, safe='')}"
        else:
            raise ValueError("wechat upload url missing")
        response = self._request(
            "POST",
            url,
            raw_body=ciphertext,
            timeout=30,
            extra_headers={"Content-Type": "application/octet-stream"},
        )
        encrypted_param = response.headers.get("x-encrypted-param", "").strip()
        if not encrypted_param:
            raise ValueError("wechat upload response missing x-encrypted-param")
        return encrypted_param

    def send_media_file(
        self,
        token: str,
        to_user_id: str,
        file_path: str | Path,
        *,
        context_token: str | None = None,
        text: str = "",
    ) -> str:
        path = Path(file_path)
        payload = path.read_bytes()
        if len(payload) > WECHAT_MEDIA_MAX_BYTES:
            raise ValueError("wechat media file too large")
        mime = get_mime_from_filename(path.name)
        if mime.startswith("image/"):
            media_type = 1
            item_type = 2
        elif mime.startswith("video/"):
            media_type = 2
            item_type = 5
        else:
            media_type = 3
            item_type = 4
        filekey = secrets.token_hex(16)
        aes_key = secrets.token_bytes(16)
        rawsize = len(payload)
        rawfilemd5 = hashlib.md5(payload).hexdigest()
        filesize = _aes_ecb_padded_size(rawsize)
        upload_meta = self._get_upload_url(
            token,
            {
                "filekey": filekey,
                "media_type": media_type,
                "to_user_id": to_user_id,
                "rawsize": rawsize,
                "rawfilemd5": rawfilemd5,
                "filesize": filesize,
                "no_need_thumb": True,
                "aeskey": aes_key.hex(),
            },
        )
        download_param = self._upload_ciphertext(
            payload,
            aes_key=aes_key,
            upload_full_url=upload_meta.get("upload_full_url"),
            upload_param=upload_meta.get("upload_param"),
            filekey=filekey,
        )
        aes_key_wire = base64.b64encode(aes_key.hex().encode("ascii")).decode("utf-8")
        item: dict
        if item_type == 2:
            item = {
                "type": 2,
                "image_item": {
                    "media": {
                        "encrypt_query_param": download_param,
                        "aes_key": aes_key_wire,
                        "encrypt_type": 1,
                    },
                    "mid_size": filesize,
                },
            }
        elif item_type == 5:
            item = {
                "type": 5,
                "video_item": {
                    "media": {
                        "encrypt_query_param": download_param,
                        "aes_key": aes_key_wire,
                        "encrypt_type": 1,
                    },
                    "video_size": filesize,
                },
            }
        else:
            item = {
                "type": 4,
                "file_item": {
                    "media": {
                        "encrypt_query_param": download_param,
                        "aes_key": aes_key_wire,
                        "encrypt_type": 1,
                    },
                    "file_name": path.name,
                    "len": str(rawsize),
                },
            }
        last_client_id = ""
        for packet in ([{"type": 1, "text_item": {"text": text}}] if text else []) + [item]:
            last_client_id = f"gemen-wechat-{uuid.uuid4().hex}"
            self._request(
                "POST",
                "ilink/bot/sendmessage",
                body={
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": to_user_id,
                        "client_id": last_client_id,
                        "message_type": 2,
                        "message_state": 2,
                        "item_list": [packet],
                        "context_token": context_token or None,
                    }
                },
                token=token,
                timeout=30,
            )
        return last_client_id

    def download_media_to_path(self, item: dict, dest_dir: str | Path) -> dict:
        dest_root = Path(dest_dir)
        dest_root.mkdir(parents=True, exist_ok=True)
        item_type = int(item.get("type") or 0)
        if item_type == 2:
            image_item = item.get("image_item") or {}
            media = image_item.get("media") or {}
            full_url = (media.get("full_url") or "").strip()
            encrypt_query_param = (media.get("encrypt_query_param") or "").strip()
            if not full_url and not encrypt_query_param:
                raise ValueError("wechat image item missing media url")
            if full_url:
                url = full_url
            else:
                url = f"{self.cdn_base_url}/download?encrypted_query_param={requests.utils.quote(encrypt_query_param, safe='')}"
            response = self._request("GET", url, timeout=30)
            content = response.content
            if image_item.get("aeskey"):
                content = _aes_ecb_decrypt(content, bytes.fromhex(str(image_item["aeskey"])))
            elif media.get("aes_key"):
                content = _aes_ecb_decrypt(content, _parse_aes_key_base64(str(media["aes_key"])))
            filename = f"{uuid.uuid4().hex}.jpg"
            path = dest_root / filename
            path.write_bytes(content)
            return {"path": str(path), "filename": filename, "media_type": "image/jpeg"}
        if item_type == 4:
            file_item = item.get("file_item") or {}
            media = file_item.get("media") or {}
            full_url = (media.get("full_url") or "").strip()
            encrypt_query_param = (media.get("encrypt_query_param") or "").strip()
            if not full_url and not encrypt_query_param:
                raise ValueError("wechat file item missing media url")
            if full_url:
                url = full_url
            else:
                url = f"{self.cdn_base_url}/download?encrypted_query_param={requests.utils.quote(encrypt_query_param, safe='')}"
            response = self._request("GET", url, timeout=30)
            content = response.content
            if media.get("aes_key"):
                content = _aes_ecb_decrypt(content, _parse_aes_key_base64(str(media["aes_key"])))
            filename = str(file_item.get("file_name") or f"{uuid.uuid4().hex}.bin")
            path = dest_root / filename
            path.write_bytes(content)
            return {"path": str(path), "filename": filename, "media_type": get_mime_from_filename(filename)}
        if item_type == 5:
            video_item = item.get("video_item") or {}
            media = video_item.get("media") or {}
            full_url = (media.get("full_url") or "").strip()
            encrypt_query_param = (media.get("encrypt_query_param") or "").strip()
            if not full_url and not encrypt_query_param:
                raise ValueError("wechat video item missing media url")
            if full_url:
                url = full_url
            else:
                url = f"{self.cdn_base_url}/download?encrypted_query_param={requests.utils.quote(encrypt_query_param, safe='')}"
            response = self._request("GET", url, timeout=30)
            content = response.content
            if media.get("aes_key"):
                content = _aes_ecb_decrypt(content, _parse_aes_key_base64(str(media["aes_key"])))
            filename = f"{uuid.uuid4().hex}.mp4"
            path = dest_root / filename
            path.write_bytes(content)
            return {"path": str(path), "filename": filename, "media_type": "video/mp4"}
        if item_type == 3:
            voice_item = item.get("voice_item") or {}
            media = voice_item.get("media") or {}
            full_url = (media.get("full_url") or "").strip()
            encrypt_query_param = (media.get("encrypt_query_param") or "").strip()
            if not full_url and not encrypt_query_param:
                raise ValueError("wechat voice item missing media url")
            if full_url:
                url = full_url
            else:
                url = f"{self.cdn_base_url}/download?encrypted_query_param={requests.utils.quote(encrypt_query_param, safe='')}"
            response = self._request("GET", url, timeout=30)
            content = response.content
            if media.get("aes_key"):
                content = _aes_ecb_decrypt(content, _parse_aes_key_base64(str(media["aes_key"])))
            filename = f"{uuid.uuid4().hex}.silk"
            path = dest_root / filename
            path.write_bytes(content)
            return {"path": str(path), "filename": filename, "media_type": "audio/silk"}
        raise ValueError(f"unsupported wechat media item type: {item_type}")
