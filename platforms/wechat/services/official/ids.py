"""Stable local id helpers for WeChat peers/scopes."""

from __future__ import annotations

import hashlib


def local_user_id_for_wechat(peer_id: str) -> int:
    digest = hashlib.sha256(f"wechat:{peer_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    return value or 1


def local_chat_id_for_wechat(scope_id: str) -> int:
    digest = hashlib.sha256(f"wechat-chat:{scope_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    return value or 1
