"""Message and control API mixin."""

from __future__ import annotations

import uuid

import requests


class ClientMessagesMixin:
    def fetch_qr_code(self) -> dict:
        return self._request("GET", f"ilink/bot/get_bot_qrcode?bot_type={self.bot_type}", timeout=15).json()

    def poll_qr_status(self, qrcode: str, *, timeout_ms: int = 35_000) -> dict:
        try:
            resp = self._request("GET", f"ilink/bot/get_qrcode_status?qrcode={requests.utils.quote(qrcode, safe='')}", timeout=max(1.0, timeout_ms / 1000))
            return resp.json()
        except requests.Timeout:
            return {"status": "wait"}

    def get_updates(self, token: str, get_updates_buf: str, *, timeout_ms: int = 35_000) -> dict:
        try:
            resp = self._request("POST", "ilink/bot/getupdates", body={"get_updates_buf": get_updates_buf or "", "base_info": {"channel_version": "python-gemen-wechat"}}, token=token, timeout=max(1.0, timeout_ms / 1000))
            return resp.json()
        except requests.Timeout:
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf or ""}

    def get_config(self, token: str, ilink_user_id: str, *, context_token: str | None = None) -> dict:
        return self._request("POST", "ilink/bot/getconfig", body={"ilink_user_id": ilink_user_id, "context_token": context_token or ""}, token=token, timeout=10).json()

    def send_typing(self, token: str, ilink_user_id: str, typing_ticket: str, *, status: int) -> dict:
        return self._request("POST", "ilink/bot/sendtyping", body={"ilink_user_id": ilink_user_id, "typing_ticket": typing_ticket, "status": int(status)}, token=token, timeout=10).json()

    def send_text_message(self, token: str, to_user_id: str, text: str, *, context_token: str | None = None) -> str:
        client_id = f"gemen-wechat-{uuid.uuid4().hex}"
        self._logger.info("WeChat sendmessage text: to=%s client_id=%s len=%s has_context=%s", to_user_id, client_id, len(text or ""), bool(context_token))
        self._send_message_packet(token=token, to_user_id=to_user_id, client_id=client_id, packet={"type": 1, "text_item": {"text": text}}, context_token=context_token, timeout=15)
        return client_id

    def _send_message_packet(self, *, token: str, to_user_id: str, client_id: str, packet: dict, context_token: str | None, timeout: float) -> None:
        self._request(
            "POST",
            "ilink/bot/sendmessage",
            body={"msg": {"from_user_id": "", "to_user_id": to_user_id, "client_id": client_id, "message_type": 2, "message_state": 2, "item_list": [packet], "context_token": context_token or None}},
            token=token,
            timeout=timeout,
        )
