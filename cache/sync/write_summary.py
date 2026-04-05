"""Sync summary logging."""

from __future__ import annotations

from .constants import SYNC_LOG_LABELS


def log_sync_summary(logger, dirty: dict) -> None:
    parts = [f"{len(dirty[key])} {label}" for key, label in SYNC_LOG_LABELS.items() if dirty.get(key)]
    if parts:
        logger.info("Synced to DB: %s", ", ".join(parts))
