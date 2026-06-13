"""Heartbeat logging context for long-running cron tasks."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def _heartbeat_monitor(user_id: int, task_name: str):
    task_start = time.time()
    phase = ["init"]
    stop_event = threading.Event()

    def _loop():
        while not stop_event.wait(10):
            elapsed = int(time.time() - task_start)
            logger.info(
                "[user=%d] cron task '%s': %s (%ds)",
                user_id,
                task_name,
                phase[0],
                elapsed,
            )

    hb = threading.Thread(target=_loop, daemon=True)
    hb.start()
    try:
        yield phase
    finally:
        stop_event.set()
        hb.join(timeout=1)
