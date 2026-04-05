"""Media upload/send mixin."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from pathlib import Path

import requests

from .constants import WECHAT_MEDIA_MAX_BYTES
from .crypto import aes_ecb_encrypt, aes_ecb_padded_size
from .mime_types import get_mime_from_filename


class ClientMediaSendMixin:
    def _get_upload_url(self, token: str, payload: dict) -> dict:
        return self._request("POST", "ilink/bot/getuploadurl", body=payload, token=token, timeout=15).json()

    def _upload_ciphertext(self, plaintext: bytes, *, aes_key: bytes, upload_full_url: str | None, upload_param: str | None, filekey: str) -> str:
        ciphertext = aes_ecb_encrypt(plaintext, aes_key)
        if upload_full_url:
            url = upload_full_url.strip()
        elif upload_param:
            quoted = requests.utils.quote(upload_param, safe="")
            url = f"{self.cdn_base_url}/upload?encrypted_query_param={quoted}&filekey={requests.utils.quote(filekey, safe='')}"
        else:
            raise ValueError("wechat upload url missing")
        response = self._request("POST", url, raw_body=ciphertext, timeout=30, extra_headers={"Content-Type": "application/octet-stream"})
        encrypted_param = response.headers.get("x-encrypted-param", "").strip()
        if not encrypted_param:
            raise ValueError("wechat upload response missing x-encrypted-param")
        return encrypted_param

    def send_media_file(self, token: str, to_user_id: str, file_path: str | Path, *, context_token: str | None = None, text: str = "") -> str:
        path = Path(file_path)
        payload = path.read_bytes()
        if len(payload) > WECHAT_MEDIA_MAX_BYTES:
            raise ValueError("wechat media file too large")
        mime = get_mime_from_filename(path.name)
        media_type, item_type = (1, 2) if mime.startswith("image/") else ((2, 5) if mime.startswith("video/") else (3, 4))
        filekey = secrets.token_hex(16)
        aes_key = secrets.token_bytes(16)
        rawsize = len(payload)
        upload_meta = self._get_upload_url(token, {"filekey": filekey, "media_type": media_type, "to_user_id": to_user_id, "rawsize": rawsize, "rawfilemd5": hashlib.md5(payload).hexdigest(), "filesize": aes_ecb_padded_size(rawsize), "no_need_thumb": True, "aeskey": aes_key.hex()})
        download_param = self._upload_ciphertext(payload, aes_key=aes_key, upload_full_url=upload_meta.get("upload_full_url"), upload_param=upload_meta.get("upload_param"), filekey=filekey)
        aes_key_wire = base64.b64encode(aes_key.hex().encode("ascii")).decode("utf-8")
        item = _build_media_item(item_type, download_param, aes_key_wire, path.name, rawsize, aes_ecb_padded_size(rawsize))
        last_client_id = ""
        packets = ([{"type": 1, "text_item": {"text": text}}] if text else []) + [item]
        for packet in packets:
            last_client_id = f"gemen-wechat-{uuid.uuid4().hex}"
            self._logger.info("WeChat sendmessage media: to=%s client_id=%s packet_type=%s has_context=%s", to_user_id, last_client_id, packet.get("type"), bool(context_token))
            self._send_message_packet(token=token, to_user_id=to_user_id, client_id=last_client_id, packet=packet, context_token=context_token, timeout=30)
        return last_client_id


def _build_media_item(item_type: int, download_param: str, aes_key_wire: str, filename: str, rawsize: int, filesize: int) -> dict:
    media = {"encrypt_query_param": download_param, "aes_key": aes_key_wire, "encrypt_type": 1}
    if item_type == 2:
        return {"type": 2, "image_item": {"media": media, "mid_size": filesize}}
    if item_type == 5:
        return {"type": 5, "video_item": {"media": media, "video_size": filesize}}
    return {"type": 4, "file_item": {"media": media, "file_name": filename, "len": str(rawsize)}}
