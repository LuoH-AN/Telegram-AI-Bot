"""In-memory TTL cache of pending group file uploads (NapCat group_upload).

Each group member can have one pending upload. Used so that QQ groups can
support `/persona prompt` after uploading a .txt file separately (since
QQ group file uploads arrive as `notice.group_upload` events with no
caption).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

TTL_SECONDS = 300


@dataclass(frozen=True)
class PendingUpload:
    file_id: str
    file_name: str
    timestamp: float


_store: dict[tuple[int, int], PendingUpload] = {}


def _prune_expired(now: float | None = None) -> None:
    cutoff = (now if now is not None else time.time()) - TTL_SECONDS
    stale = [k for k, v in _store.items() if v.timestamp < cutoff]
    for k in stale:
        _store.pop(k, None)


def remember_upload(group_id: int, user_id: int, *, file_id: str, file_name: str) -> None:
    if not file_id:
        return
    _prune_expired()
    _store[(int(group_id), int(user_id))] = PendingUpload(
        file_id=str(file_id), file_name=str(file_name or ""), timestamp=time.time(),
    )


def consume_upload(group_id: int, user_id: int) -> PendingUpload | None:
    _prune_expired()
    return _store.pop((int(group_id), int(user_id)), None)


def peek_upload(group_id: int, user_id: int) -> PendingUpload | None:
    _prune_expired()
    return _store.get((int(group_id), int(user_id)))


def capture_group_upload_notice(event: dict) -> PendingUpload | None:
    """Extract file info from a group_upload notice and remember it."""
    group_id = event.get("group_id")
    user_id = event.get("user_id")
    file_info = event.get("file") or {}
    file_id = file_info.get("id") or file_info.get("file_id") or ""
    file_name = file_info.get("name") or file_info.get("file_name") or ""
    if not (group_id and user_id and file_id):
        return None
    remember_upload(int(group_id), int(user_id), file_id=str(file_id), file_name=str(file_name))
    return _store.get((int(group_id), int(user_id)))
