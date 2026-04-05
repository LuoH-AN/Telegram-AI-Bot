"""Message text extraction and simple filters."""

from __future__ import annotations

from utils import is_image_file

from ..config import WECHAT_COMMAND_PREFIX, WECHAT_GROUP_MENTION_ALIASES, WECHAT_GROUP_REPLY_ALL, WECHAT_VIDEO_SUFFIXES


def extract_text_body(item_list: list[dict]) -> str:
    def _body_from_item(item: dict) -> str:
        item_type = int(item.get("type") or 0)
        if item_type == 1:
            text = str((item.get("text_item") or {}).get("text") or "").strip()
            ref_msg = item.get("ref_msg") or {}
            if not ref_msg:
                return text
            ref_item = ref_msg.get("message_item") or {}
            if int(ref_item.get("type") or 0) in {2, 3, 4, 5}:
                return text
            title = str(ref_msg.get("title") or "").strip()
            ref_text = _body_from_item(ref_item)
            parts = [part for part in (title, ref_text) if part]
            if not parts:
                return text
            quoted = f"[Quoted: {' | '.join(parts)}]"
            return f"{quoted}\n{text}" if text else quoted
        if item_type == 3:
            return str((item.get("voice_item") or {}).get("text") or "").strip()
        return ""

    for item in item_list:
        text = _body_from_item(item)
        if text:
            return text
    return ""


def strip_wechat_group_mentions(text: str) -> str:
    cleaned = text or ""
    for alias in WECHAT_GROUP_MENTION_ALIASES:
        cleaned = cleaned.replace(f"@{alias}", "").replace(f"＠{alias}", "")
    return cleaned.strip()


def should_respond_in_wechat_group(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.startswith(WECHAT_COMMAND_PREFIX) or WECHAT_GROUP_REPLY_ALL:
        return True
    lowered = stripped.lower()
    for alias in WECHAT_GROUP_MENTION_ALIASES:
        alias_lower = alias.strip().lower()
        if not alias_lower:
            continue
        if f"@{alias_lower}" in lowered or f"＠{alias_lower}" in lowered:
            return True
        if alias_lower in lowered and len(alias_lower) >= 3:
            return True
    return False


def wechat_media_type_code_for_path(file_path: str) -> int:
    lower_path = file_path.lower()
    if is_image_file(file_path):
        return 2
    if lower_path.endswith(WECHAT_VIDEO_SUFFIXES):
        return 5
    return 4
