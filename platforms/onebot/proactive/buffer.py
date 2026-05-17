"""Per-group ring buffer of recent chat lines for chatroom-style context."""

from __future__ import annotations

import os
import time
from collections import deque
from datetime import datetime

_DEFAULT_MAX = 30
try:
    _MAX = max(5, int(os.getenv("QQ_GROUP_BUFFER_SIZE", "0") or _DEFAULT_MAX))
except ValueError:
    _MAX = _DEFAULT_MAX

_buffers: dict[int, deque[str]] = {}
_last_seen: dict[int, float] = {}


def _append(group_id: int, line: str) -> None:
    if not line or not group_id:
        return
    buf = _buffers.setdefault(int(group_id), deque(maxlen=_MAX))
    buf.append(line)
    _last_seen[int(group_id)] = time.time()


def record_user(group_id: int, nickname: str, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    nick = (nickname or "User").strip()[:24] or "User"
    _append(int(group_id), f"[{nick}/{ts}]: {text}")


def record_bot(group_id: int, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    _append(int(group_id), f"[You/{ts}]: {text}")


def get_recent_lines(group_id: int, *, exclude_last: int = 0) -> list[str]:
    buf = _buffers.get(int(group_id))
    if not buf:
        return []
    lines = list(buf)
    if exclude_last > 0:
        lines = lines[: max(0, len(lines) - exclude_last)]
    return lines


def clear_group(group_id: int) -> None:
    _buffers.pop(int(group_id), None)
    _last_seen.pop(int(group_id), None)


def buffer_size() -> int:
    return _MAX


def extract_nickname(raw_event: dict) -> str:
    sender = raw_event.get("sender") if isinstance(raw_event, dict) else None
    if not isinstance(sender, dict):
        return "User"
    card = str(sender.get("card") or "").strip()
    nickname = str(sender.get("nickname") or "").strip()
    return card or nickname or f"u{sender.get('user_id') or '?'}"
