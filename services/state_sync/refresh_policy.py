"""Refresh throttling policy."""

import os
import threading
import time

STATE_REFRESH_INTERVAL = max(0.5, float(os.getenv("STATE_REFRESH_INTERVAL", "2.0")))

_refresh_lock = threading.Lock()
_last_refresh_ts: dict[int, float] = {}


def should_refresh(user_id: int, force: bool) -> bool:
    if force:
        return True
    now = time.monotonic()
    with _refresh_lock:
        last = _last_refresh_ts.get(user_id, 0.0)
        if now - last < STATE_REFRESH_INTERVAL:
            return False
        _last_refresh_ts[user_id] = now
    return True

