"""Runtime lifecycle for DB sync thread."""

from __future__ import annotations

import logging
import threading
import time

from config import DB_SYNC_INTERVAL
from database import get_connection
from database.schema import create_tables

logger = logging.getLogger(__name__)


def sync_loop(sync_func) -> None:
    while True:
        time.sleep(DB_SYNC_INTERVAL)
        try:
            sync_func()
        except Exception:
            logger.exception("Sync error")


def init_database(cache, load_func, sync_func) -> None:
    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        try:
            with get_connection() as conn:
                create_tables(conn)
            break
        except Exception as exc:
            pgcode = getattr(exc, "pgcode", None)
            deadlock = pgcode == "40P01" or "deadlock detected" in str(exc).lower()
            if not deadlock or attempt >= max_attempts:
                raise
            backoff = min(0.4 * (2 ** (attempt - 1)), 5.0)
            logger.warning(
                "Database schema init deadlock (attempt %d/%d), retrying in %.1fs",
                attempt,
                max_attempts,
                backoff,
            )
            time.sleep(backoff)

    load_func(cache)
    threading.Thread(target=sync_loop, args=(sync_func,), daemon=True).start()
    logger.info("Database initialized, cache loaded")
